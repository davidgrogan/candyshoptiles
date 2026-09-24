"""Order-request notification email via Resend's HTTPS API.

Not SMTP: outbound SMTP is blocked from the droplet, and a hung SMTP
connection once took down a whole gunicorn worker on Paradise City Music.
This uses a short timeout and never raises -- the order is already saved
before this runs, and shows up in Admin -> Orders whether or not the email
goes out.
"""
import requests
from flask import current_app, url_for

from app.pricing import money


def send_order_notification(order):
    cfg = current_app.config
    if not cfg.get("RESEND_API_KEY") or not cfg.get("ORDER_NOTIFY_EMAIL"):
        current_app.logger.info("Order #%s saved; email not configured, skipping notification.", order.id)
        return False

    lines = [
        f"New order request #{order.id} -- {money(order.total_cents)}",
        "",
        f"Name:  {order.name}",
        f"Email: {order.email}",
        f"Phone: {order.phone or '-'}",
        "",
        f"Tiles: {order.tile_count}",
        f"Sample tile: {order.sample_image_title if order.include_sample else 'no'}",
        "",
        "Ship to:",
        order.address or "-",
        "",
        "Notes:",
        order.notes or "-",
        "",
        f"View it: {url_for('admin.order_detail', order_id=order.id, _external=True)}",
    ]
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {cfg['RESEND_API_KEY']}"},
            json={
                "from": cfg["RESEND_FROM_EMAIL"],
                "to": [cfg["ORDER_NOTIFY_EMAIL"]],
                "reply_to": order.email,
                "subject": f"Candy Shop Tiles order request #{order.id} ({money(order.total_cents)})",
                "text": "\n".join(lines),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException:
        current_app.logger.exception("Order #%s saved, but the notification email failed.", order.id)
        return False
