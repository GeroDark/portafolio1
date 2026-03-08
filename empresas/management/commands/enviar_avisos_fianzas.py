# empresas/management/commands/enviar_avisos_fianzas.py
from django.core.management.base import BaseCommand
from empresas.tasks import procesar_avisos_fianzas

class Command(BaseCommand):
    help = "Envía avisos de vencimiento (20..15 días) para cartas fianza no liquidadas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="No envía, solo lista los candidatos.")

    def handle(self, *args, **opts):
        procesar_avisos_fianzas(dry_run=opts["dry_run"], stdout=self.stdout)
