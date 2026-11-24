"""Bakgrundsjobb: inläsning och analys körs i en egen tråd med förlopp, så webbsidan aldrig låser sig.

Ett jobb i taget kör per kö (de delar databasen); fler köas. Sidan frågar efter förloppet varje sekund.
2.75: nattberäkningen har en egen kö ("natt") så att den inte stoppar analys, visning eller export.
Den håller huvudkön bara under de korta stegen som skriver (inläsning och fakta), och använder en egen
databasanslutning – WAL-läget i SQLite låter läsare och en skrivare arbeta samtidigt.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    title: str
    status: str = "väntar"          # väntar, kör, klar, fel, avbruten (2.88)
    stage: str = "Väntar på tur"
    done: int = 0
    total: int = 0
    started: float = field(default_factory=time.time)
    finished: float | None = None
    result: object = None           # jobbets resultat (för analyser: vy-id och sida)
    error: str | None = None        # meddelande till användaren
    log: list = field(default_factory=list)
    cancel_requested: bool = False  # 2.88: avbryt-knappen
    cleanup: list = field(default_factory=list)  # 2.88: filer som tas bort om jobbet avbryts

    def check(self) -> None:
        """2.88: avbryt jobbet här om användaren tryckt Avbryt (anropas också från set())."""
        if self.cancel_requested:
            raise JobCancelled()

    def set(self, stage: str, done: int = 0, total: int = 0) -> None:
        self.check()
        if stage != self.stage:
            self.log.append((round(time.time() - self.started, 1), stage))
        self.stage, self.done, self.total = stage, done, total

    def as_dict(self) -> dict:
        eta = None
        if self.total and self.done and self.status == "kör":
            el = time.time() - self._stage_t0()
            eta = el / self.done * (self.total - self.done)
        return {"id": self.id, "status": self.status, "stage": self.stage, "done": self.done, "total": self.total,
                "elapsed": round(time.time() - self.started, 1), "eta": round(eta) if eta else None,
                "error": self.error, "cancel": self.cancel_requested}

    def _stage_t0(self) -> float:
        return self.started + (self.log[-1][0] if self.log else 0.0)


class JobManager:
    def __init__(self, keep: int = 6):
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.keep = keep
        self.lock = threading.Lock()      # skyddar ordlistan
        self.run_lock = threading.Lock()  # ett tungt jobb i taget i huvudkön
        self.lanes = {"main": self.run_lock, "natt": threading.Lock()}

    def active(self) -> list:
        """Jobb som väntar eller kör (i startordning) – visas i jobbraden överst på alla sidor."""
        with self.lock:
            return [self.jobs[j] for j in self.order if self.jobs[j].status in ("väntar", "kör")]

    def start(self, title: str, fn, *args, key: str | None = None, lane: str = "main") -> Job:
        """key: samma sorts jobb som redan väntar eller kör startas inte en gång till – det pågående returneras
        (2.72: djupanalysen köades två gånger när man gick tillbaka till sidan och tryckte igen)."""
        job = Job(id=uuid.uuid4().hex[:12], title=title)
        job.key = key
        job.lane = lane
        lock = self.lanes.get(lane, self.run_lock)
        with self.lock:   # 2.80: kontroll och registrering i samma lås (två samtidiga beställningar)
            if key is not None:
                for jid in self.order:
                    j = self.jobs[jid]
                    if getattr(j, "key", None) == key and j.status in ("väntar", "kör"):
                        return j
            self.jobs[job.id] = job
            self.order.append(job.id)
            # släng gamla avslutade jobb (aldrig ett som kör eller väntar)
            done = [j for j in self.order if self.jobs[j].status in ("klar", "fel", "avbruten")]
            while len(self.order) > self.keep and done:
                old = done.pop(0)
                self.order.remove(old)
                self.jobs.pop(old, None)

        def run():
            with lock:
                if job.cancel_requested:   # avbrutet medan det väntade i kön
                    job.status, job.stage, job.finished = "avbruten", "Avbrutet", time.time()
                    return
                job.status = "kör"
                try:
                    job.result = fn(job, *args)
                    job.status = "klar"
                except JobCancelled:
                    job.status, job.stage = "avbruten", "Avbrutet"
                    _remove(job.cleanup)
                except UserError as e:
                    job.error = str(e)
                    job.status = "fel"
                except Exception:  # oväntat fel – visa tekniska detaljer så de kan skickas till Claude
                    job.error = "Ett oväntat fel inträffade:\n" + traceback.format_exc(limit=6)
                    job.status = "fel"
                finally:
                    job.finished = time.time()

        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, jid: str) -> Job | None:
        with self.lock:
            return self.jobs.get(jid)

    def cancel(self, jid: str) -> bool:
        """2.88: begär avbrott. Jobbet slutar vid nästa förloppssteg (oftast inom några sekunder)."""
        with self.lock:
            j = self.jobs.get(jid)
            if j is None or j.status not in ("väntar", "kör"):
                return False
            j.cancel_requested = True
            j.stage = "Avbryter …"
            return True


def _remove(paths) -> None:
    import os
    for p in paths or []:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


class JobCancelled(BaseException):
    """2.88: jobbet avbröts av användaren. BaseException så att inga `except Exception` i jobben sväljer avbrottet."""


class UserError(Exception):
    """Fel som beror på indata (t.ex. tomt urval). Meddelandet visas för användaren."""


MANAGER = JobManager()
