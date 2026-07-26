"""
Delivery-channel foundation.

The business has no Zalo Official Account yet, so nothing is actually
transmitted — messages are queued for staff to relay by phone. The
foundation exists so connecting Zalo later is a credentials-and-one-
method change.

The property worth protecting above all others: a message must NEVER be
recorded as "sent" unless something really sent it. Staff read that
status to decide whether they still need to phone the customer, so a
false positive silently drops a real person's ride information.
"""

import pytest

from app.services import messaging
from app.services.messaging import (
    STATUS_FAILED,
    STATUS_PENDING_MANUAL,
    STATUS_SENT,
    ManualRelayChannel,
    ZaloChannel,
    active_channel,
    deliver,
)


def test_with_no_zalo_token_the_active_channel_is_manual_relay():
    assert isinstance(active_channel(), ManualRelayChannel)


def test_delivery_reports_pending_relay_not_sent():
    result = deliver(phone="0912345678", message="test")
    assert result.channel == "manual"
    assert result.status == STATUS_PENDING_MANUAL
    assert result.status != STATUS_SENT, (
        "a message nobody transmitted must never be recorded as sent — "
        "staff use that status to decide whether to phone the customer"
    )


def test_manual_relay_is_always_available_so_nothing_is_ever_dropped():
    assert ManualRelayChannel().available() is True


def test_zalo_is_unavailable_without_a_token():
    assert ZaloChannel().available() is False


def test_zalo_refuses_to_pretend_it_sent_something(monkeypatch):
    # Even with a token present, the send path is genuinely unimplemented
    # and says so rather than returning a fabricated success.
    monkeypatch.setattr(
        messaging.settings, "zalo_oa_token", "fake-token", raising=False
    )
    channel = ZaloChannel()
    assert channel.available() is True
    with pytest.raises(NotImplementedError):
        channel.send(phone="0912345678", message="test")


def test_a_broken_real_channel_falls_back_instead_of_raising(monkeypatch):
    # A notification failing must not take a dispatch down with it — the
    # trip still has to seal.
    monkeypatch.setattr(
        messaging.settings, "zalo_oa_token", "fake-token", raising=False
    )
    result = deliver(phone="0912345678", message="test")

    assert result.status == STATUS_FAILED
    assert result.status != STATUS_SENT
    assert "relay by phone" in (result.detail or ""), (
        "a failed delivery must tell staff to fall back to a phone call"
    )


def test_channel_preference_puts_manual_relay_last():
    # Manual relay is the always-available backstop, so it must sit at
    # the end of the preference list or a real channel would never be
    # reached once one exists.
    assert isinstance(messaging._CHANNELS[-1], ManualRelayChannel)
    assert any(isinstance(c, ZaloChannel) for c in messaging._CHANNELS)
