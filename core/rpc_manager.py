"""
Discord RPC Manager.
- connects with pypresence
- automatic reconnect (if Discord closes or network drops)
- diff check: does not resend identical payloads
- rate limit protection
- force resync: resends the last payload after reconnect
"""

import time
import logging
from typing import Optional

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, PipeClosed, InvalidID, InvalidPipe

from .state_machine import RPCPayload

logger = logging.getLogger(__name__)

MIN_UPDATE_INTERVAL = 2.0
RECONNECT_DELAY = 5.0 
# Periodic resync: force update at regular intervals even if Discord appears connected
# This helps detect if Discord went unsynced in the background for any reason.
PERIODIC_RESYNC_INTERVAL = 60.0


class RPCManager:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.rpc: Optional[Presence] = None
        self.connected = False
        self.last_signature: tuple = ()
        self.last_payload: Optional[RPCPayload] = None
        self.last_update_time: float = 0
        self.last_reconnect_attempt: float = 0
        self.last_resync_time: float = 0
        self._consecutive_failures: int = 0

    def connect(self) -> bool:
        if self.connected:
            return True
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            # NEW: new connection = reset state, force resend last payload on next tick
            self.last_signature = ()
            self.last_update_time = 0
            self._consecutive_failures = 0
            logger.info("Connected to Discord.")
            # If there is a last payload, resend it immediately (resync)
            if self.last_payload:
                logger.info("Resending last payload after reconnect...")
                self._send_update(self.last_payload, force=True)
            return True
        except DiscordNotFound:
            logger.debug("Discord is not open.")
            self.connected = False
            return False
        except (InvalidID, InvalidPipe) as e:
            logger.error(f"Discord connection error: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected connection error: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.rpc and self.connected:
            try:
                self.rpc.close()
            except Exception:
                pass
        self.connected = False
        self.rpc = None

    def try_reconnect(self) -> bool:
        now = time.time()
        if (now - self.last_reconnect_attempt) < RECONNECT_DELAY:
            return False
        self.last_reconnect_attempt = now
        self.disconnect()
        return self.connect()

    def force_resync(self):
        """
        Periodic force resync - resend the last payload even if Discord appears connected.
        This helps recover from hidden unsyncs or transient network glitches.
        """
        if self.connected and self.last_payload:
            logger.debug("Periodic force resync.")
            self._send_update(self.last_payload, force=True)
            self.last_resync_time = time.time()

    def update(self, payload: Optional[RPCPayload]) -> bool:
        """
        Send the payload to Discord.
        - None: clear the RPC (LoL closed)
        - skip if the same payload was already sent (diff check)
        - respect rate limits
        - if reconnect happened, force resend
        """
        if not self.connected:
            if not self.try_reconnect():
                return False

        # Periodic resync check
        now = time.time()
        if (now - self.last_resync_time) >= PERIODIC_RESYNC_INTERVAL:
            if self.last_payload and payload is not None:
                # reset last_signature so this update is forced
                self.last_signature = ()
                self.last_resync_time = now

        # If payload is None, clear the RPC
        if payload is None:
            self.last_payload = None  # clear cache
            if self.last_signature:
                try:
                    self.rpc.clear()
                    self.last_signature = ()
                    logger.info("RPC cleared.")
                    self._consecutive_failures = 0
                    return True
                except (PipeClosed, BrokenPipeError, ConnectionResetError, OSError):
                    self._on_failure()
                    return False
                except Exception as e:
                    logger.warning(f"RPC clear error: {e}")
                    return False
            return True

        # Diff check
        signature = payload.compute_signature()
        if signature == self.last_signature:
            return True

        # Rate limit
        if (now - self.last_update_time) < MIN_UPDATE_INTERVAL:
            return False

        return self._send_update(payload)

    def _send_update(self, payload: RPCPayload, force: bool = False) -> bool:
        """Send the actual update. force=True bypasses rate limit and diff check."""
        if not self.connected:
            return False

        kwargs = self._payload_to_kwargs(payload)
        try:
            self.rpc.update(**kwargs)
            self.last_signature = payload.compute_signature()
            self.last_payload = payload  # NEW: cache it
            self.last_update_time = time.time()
            self._consecutive_failures = 0
            tag = "[FORCE]" if force else f"[{payload.state_name.value}]"
            logger.info(f"{tag} {payload.details} | {payload.state}")
            return True
        except (PipeClosed, BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.warning(f"Discord pipe closed ({type(e).__name__}), reconnect will be attempted.")
            self._on_failure()
            return False
        except Exception as e:
            logger.error(f"RPC update error: {e}")
            self._on_failure()
            return False

    def _on_failure(self):
        """Mark the connection as dead on failure."""
        self._consecutive_failures += 1
        self.connected = False
        # keep last_payload so it can be resent after reconnect

    @staticmethod
    def _payload_to_kwargs(payload: RPCPayload) -> dict:
        kwargs = {}
        if payload.details:
            kwargs["details"] = payload.details[:128]
        if payload.state:
            kwargs["state"] = payload.state[:128]
        if payload.large_image:
            kwargs["large_image"] = payload.large_image
        if payload.large_text:
            kwargs["large_text"] = payload.large_text[:128]
        if payload.small_image:
            kwargs["small_image"] = payload.small_image
        if payload.small_text:
            kwargs["small_text"] = payload.small_text[:128]
        if payload.start:
            kwargs["start"] = payload.start
        return kwargs