"""
How a composed message actually reaches a customer.

notification_service decides WHAT to say; this decides HOW it gets
there. They're separate because the wording is settled and the delivery
channel is not: this business currently has no Zalo Official Account or
SMS gateway, so every message is queued for a staff member to relay by
phone.

The foundation exists so that connecting Zalo later is a credentials-
and-one-class change rather than a rewrite. What is deliberately NOT
done here: reporting a message as "sent" when nothing was sent. A
delivery log that lies is worse than no delivery log — staff would stop
phoning customers because the screen says the message went out.

To connect Zalo:
  1. Register a Zalo Official Account and get an OA access token.
  2. Set ZALO_OA_TOKEN in the environment (see .env.example).
  3. Fill in ZaloChannel.send below with the real API call.
Nothing else changes — notification_service, the models, the staff-
facing list and every caller already route through here.
"""

import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


# Notification.status values. `pending_manual_relay` is the honest
# default: composed, stored, waiting for a human to pass it on.
STATUS_PENDING_MANUAL = "pending_manual_relay"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class DeliveryResult:
    """What actually happened to one message."""

    channel: str
    status: str
    detail: str | None = None


class MessageChannel:
    """A way of getting a message to a customer."""

    name = "base"

    def available(self) -> bool:
        """Whether this channel is configured and usable right now."""
        raise NotImplementedError

    def send(self, *, phone: str, message: str) -> DeliveryResult:
        raise NotImplementedError


class ManualRelayChannel:
    """
    The current reality: nothing is transmitted. The message is stored
    and surfaced to staff (see /api/v1/notifications), who call or Zalo
    the customer themselves — which is how this business already
    operates, since customers book by phone in the first place.

    Always available, so there is never a path where a message is
    composed and then silently dropped.
    """

    name = "manual"

    def available(self) -> bool:
        return True

    def send(self, *, phone: str, message: str) -> DeliveryResult:
        return DeliveryResult(
            channel=self.name,
            status=STATUS_PENDING_MANUAL,
            detail="queued for staff to relay by phone",
        )


class ZaloChannel:
    """
    Zalo Official Account delivery. NOT IMPLEMENTED — no OA is
    registered for this business yet, which is a business/admin step
    (registering the account with Zalo), not a coding one.

    `available()` returns False without a token, so the dispatcher below
    falls through to manual relay and behaviour is unchanged until real
    credentials exist. Implement `send` when they do; the surrounding
    plumbing is already correct.
    """

    name = "zalo"

    def available(self) -> bool:
        return bool(getattr(settings, "zalo_oa_token", ""))

    def send(self, *, phone: str, message: str) -> DeliveryResult:
        # Intentionally not implemented. Returning a fake "sent" here
        # would be the single most damaging thing this module could do:
        # staff would trust the screen and stop calling.
        raise NotImplementedError(
            "Zalo OA sending is not implemented yet — see this module's "
            "docstring for the three steps to enable it"
        )


# Preference order. The first available channel wins; manual relay is
# last and always available, so this can never return nothing.
_CHANNELS: list = [ZaloChannel(), ManualRelayChannel()]


def active_channel():
    """The channel that would be used for a message sent right now."""
    for channel in _CHANNELS:
        if channel.available():
            return channel
    return _CHANNELS[-1]


def deliver(*, phone: str, message: str) -> DeliveryResult:
    """
    Attempt delivery through the best available channel, falling back to
    manual relay if a real one errors.

    A channel failure must never lose the message or raise into
    dispatch — a customer notification failing is not a reason for a
    trip to fail to seal.
    """
    channel = active_channel()
    if isinstance(channel, ManualRelayChannel):
        return channel.send(phone=phone, message=message)

    try:
        return channel.send(phone=phone, message=message)
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see above
        logger.warning(
            "delivery via %s failed (%s); falling back to manual relay",
            channel.name,
            exc,
        )
        return DeliveryResult(
            channel=channel.name,
            status=STATUS_FAILED,
            detail=f"{type(exc).__name__}: {exc} — relay by phone instead",
        )
