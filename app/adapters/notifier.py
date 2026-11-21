"""Adapter desacoplado de entrega de notificações (In-App / Webhook)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings


@dataclass
class DeliveryResult:
    sucesso: bool
    canal: str
    detalhe: str


class NotificationAdapter:
    """Dispara lembretes para webhook externo quando configurado, ou entrega In-App."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enviar(self, titulo: str, mensagem: str, origem: str) -> DeliveryResult:
        webhook_url = self.settings.notification_webhook_url
        if not webhook_url:
            return DeliveryResult(
                sucesso=True,
                canal="IN_APP",
                detalhe="Notificação disponibilizada na caixa In-App do Synapse.",
            )

        payload = {
            "content": f"[{origem}] **{titulo}** — {mensagem}",
            "origem": origem,
            "titulo": titulo,
            "mensagem": mensagem,
        }
        try:
            with httpx.Client(timeout=4.0) as client:
                response = client.post(webhook_url, json=payload)
                response.raise_for_status()
                return DeliveryResult(
                    sucesso=True,
                    canal="WEBHOOK",
                    detalhe="Notificação enviada via webhook externo.",
                )
        except Exception as exc:
            return DeliveryResult(
                sucesso=False,
                canal="WEBHOOK",
                detalhe=f"Erro ao enviar webhook ({exc}); mantida para retentativa.",
            )
