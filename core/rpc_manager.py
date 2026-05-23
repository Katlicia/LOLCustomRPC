"""
Discord RPC Manager.
- Connects to Discord via pypresence
- Auto-reconnect when Discord closes/reopens or pipe drops
- Diff check: skips sending identical payloads back-to-back
- Rate-limit guard: minimum interval between updates
- Force resync: re-sends the last payload after reconnect and on a periodic timer
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
        logger.info("Connecting to Discord...")
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            self.last_signature = ()
            self.last_update_time = 0
            self._consecutive_failures = 0
            logger.info("Connected to Discord.")
            if self.last_payload:
                logger.info("Resyncing last payload after reconnect...")
                self._send_update(self.last_payload, force=True)
            return True
        except DiscordNotFound:
            logger.debug("Discord is not running.")
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
        logger.debug("Disconnecting from Discord.")
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
        logger.info("Attempting reconnect to Discord...")
        self.last_reconnect_attempt = now
        self.disconnect()
        return self.connect()

    def force_resync(self):
        """Periodic resync — re-sends the last payload even if nothing changed."""
        if self.connected and self.last_payload:
            logger.debug("Periodic force resync: re-sending last payload.")
            self._send_update(self.last_payload, force=True)
            self.last_resync_time = time.time()

    def update(self, payload: Optional[RPCPayload]) -> bool:
        """
        Send a payload to Discord.
        - None: clear RPC (LoL is closed)
        - Identical payload: skip (diff check)
        - Too soon: skip (rate limit)
        """
        if not self.connected:
            if not self.try_reconnect():
                return False

        now = time.time()
        if (now - self.last_resync_time) >= PERIODIC_RESYNC_INTERVAL:
            if self.last_payload and payload is not None:
                self.last_signature = ()
                self.last_resync_time = now

        if payload is None:
            self.last_payload = None
            if self.last_signature:
                try:
                    self.rpc.clear()
                    self.last_signature = ()
                    logger.info("RPC cleared (LoL closed).")
                    self._consecutive_failures = 0
                    return True
                except (PipeClosed, BrokenPipeError, ConnectionResetError, OSError):
                    self._on_failure()
                    return False
                except Exception as e:
                    logger.warning(f"RPC clear failed: {e}")
                    return False
            return True

        signature = payload.compute_signature()
        if signature == self.last_signature:
            return True

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
            self.last_payload = payload
            self.last_update_time = time.time()
            self._consecutive_failures = 0
            tag = "[FORCE]" if force else f"[{payload.state_name.value}]"
            logger.info(f"{tag} Payload sent — details: {payload.details!r} | state: {payload.state!r}")
            return True
        except (PipeClosed, BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.warning(f"Discord pipe lost ({type(e).__name__}), will reconnect on next tick.")
            self._on_failure()
            return False
        except Exception as e:
            logger.error(f"RPC update failed: {e}")
            self._on_failure()
            return False

    def _on_failure(self):
        """Mark connection as dead; keep last_payload so we can resync after reconnect."""
        self._consecutive_failures += 1
        logger.warning(f"Discord connection lost (failure #{self._consecutive_failures}).")
        self.connected = False

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
