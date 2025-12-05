# src/utils/pdf_generator.py

import asyncio
import os
from datetime import datetime
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from src.config.settings import Settings
from src.models.transcription import TranscriptionEvent


async def pdf_generator(
    events: List[TranscriptionEvent],
    settings: Settings,
    title: str | None = None,
) -> str:
    """
    Génère un PDF à partir d'une liste de TranscriptionEvent.
    Retourne le chemin complet du PDF généré.
    """

    # On trie les événements par date de début
    events = sorted(events, key=lambda e: e.start)

    # Dossier de sortie
    pdf_dir = os.path.join(settings.logs_dir, settings.pdf_subdir)
    os.makedirs(pdf_dir, exist_ok=True)

    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_session.pdf")
    pdf_path = os.path.join(pdf_dir, filename)

    def _build_pdf() -> None:
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Titre
        story.append(Paragraph(title or "Transcription de la session", styles["Title"]))
        story.append(Spacer(1, 0.7 * cm))

        current_date = None

        for ev in events:
            # On ignore les textes vides (bruit filtré entre autres)
            text = (ev.text or "").strip()
            if not text:
                continue

            date = ev.start.date()
            if date != current_date:
                # Nouveau jour → on ajoute un sous-titre
                if current_date is not None:
                    story.append(Spacer(1, 0.4 * cm))
                current_date = date
                story.append(Paragraph(str(date), styles["Heading2"]))
                story.append(Spacer(1, 0.3 * cm))

            time_str = ev.start.strftime("%H:%M:%S")

            # Nom du joueur / personnage
            speaker_name = ev.player or str(ev.user_id)
            if ev.character:
                speaker_label = f"{speaker_name} ({ev.character})"
            else:
                speaker_label = speaker_name

            line = f"[{time_str}] <b>{speaker_label}</b> : {text}"
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 0.2 * cm))

        doc.build(story)

    # On lance la génération dans un thread pour ne pas bloquer l'event loop
    await asyncio.to_thread(_build_pdf)

    return pdf_path
