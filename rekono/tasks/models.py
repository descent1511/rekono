from django.conf import settings
from django.db import models
from processes.models import Process
from projects.models import Project
from django.core.files import File
from resources.models import Wordlist
from security.input_validation import validate_time_amount
from targets.models import Target
from tools.enums import IntensityRank
from tools.models import Configuration, Tool
import logging
from tasks.enums import Status, TimeUnit
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Create your models here.

logger = logging.getLogger()  
class Task(models.Model):
    '''Task model.'''

    rq_job_id = models.TextField(max_length=50, blank=True, null=True)          # Job Id in the tasks queue
    target = models.ForeignKey(Target, related_name='tasks', on_delete=models.CASCADE)              # Related target
    process = models.ForeignKey(Process, blank=True, null=True, on_delete=models.SET_NULL)  # Process to be executed
    tool = models.ForeignKey(Tool, blank=True, null=True, on_delete=models.SET_NULL)        # Tool to be executed
    # Configuration to be applied (only for Tool tasks)
    configuration = models.ForeignKey(Configuration, on_delete=models.SET_NULL, blank=True, null=True)
    # Intensity to be applied in the tool executions
    intensity = models.IntegerField(choices=IntensityRank.choices, default=IntensityRank.NORMAL)
    # User that has requested the task
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    status = models.TextField(max_length=10, choices=Status.choices, default=Status.REQUESTED)  # Task status
    scheduled_at = models.DateTimeField(blank=True, null=True)                  # Date when the task will be executed
    # Amount of time before task execution
    scheduled_in = models.IntegerField(blank=True, null=True, validators=[validate_time_amount])
    # Time unit to apply to the 'sheduled in' value
    scheduled_time_unit = models.TextField(max_length=10, choices=TimeUnit.choices, blank=True, null=True)
    # Amount of time before repeat task execution
    repeat_in = models.IntegerField(blank=True, null=True, validators=[validate_time_amount])
    # Time unit to apply to the 'repeat in' value
    repeat_time_unit = models.TextField(max_length=10, choices=TimeUnit.choices, blank=True, null=True)
    creation = models.DateTimeField(auto_now_add=True)                          # Creation date
    enqueued_at = models.DateTimeField(blank=True, null=True)                   # Date at task got enqueued
    start = models.DateTimeField(blank=True, null=True)                         # Task execution start date
    end = models.DateTimeField(blank=True, null=True)                           # Task execution end date
    wordlists = models.ManyToManyField(Wordlist, related_name='wordlists', blank=True)  # Wordlists applied
    report = models.FileField(upload_to='reports/', blank=True, null=True)     # Report file

    def __str__(self) -> str:
        '''Instance representation in text format.

        Returns:
            str: String value that identifies this instance
        '''
        value = f'{self.target.project.name} - {self.target.target} - '
        if self.process:
            value += self.process.name
        elif self.tool:
            value += self.tool.name
            if self.configuration:
                value += f' - {self.configuration.name}'
        return value

    def get_project(self) -> Project:
        '''Get the related project for the instance. This will be used for authorization purposes.

        Returns:
            Project: Related project entity
        '''
        return self.target.project


    def generate_report(self):
        '''Tạo báo cáo PDF sau khi quét xong'''
        from findings.models import Vulnerability, Exploit, Port, Technology
        if self.status == Status.RUNNING:
            logger.warning(f"Task {self.id} is not completed yet. Cannot generate report.")
            return

        report_path = f'reports/{self.id}_report.pdf'
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        try:
            c = canvas.Canvas(report_path, pagesize=letter)
            c.setFont("Helvetica", 12)
            c.drawString(100, 750, f"Security Scan Report for Task ID: {self.id}")
            c.drawString(100, 730, f"Target: {self.target.target}")

            y = 700 

            vulnerabilities = Vulnerability.objects.filter(port__host__address=self.target.target)
            if vulnerabilities.exists():
                c.drawString(100, y, "Discovered Vulnerabilities:")
                y -= 20
                for vul in vulnerabilities:
                    c.drawString(120, y, f"- {vul.name} (Severity: {vul.severity})")
                    if vul.cve:
                        c.drawString(140, y - 15, f"CVE: {vul.cve}")
                    y -= 30
                    if y < 50:
                        c.showPage()
                        y = 750

            exploits = Exploit.objects.filter(vulnerability__in=vulnerabilities)
            if exploits.exists():
                c.drawString(100, y, "Available Exploits:")
                y -= 20
                for exploit in exploits:
                    c.drawString(120, y, f"- {exploit.title} (Ref: {exploit.reference})")
                    y -= 20
                    if y < 50:
                        c.showPage()
                        y = 750

            ports = Port.objects.filter(host__address=self.target.target)
            if ports.exists():
                c.drawString(100, y, "Open Ports:")
                y -= 20
                for port in ports:
                    c.drawString(120, y, f"- Port {port.port} ({port.status}) - {port.service or 'Unknown'}")
                    y -= 20
                    if y < 50:
                        c.showPage()
                        y = 750

            technologies = Technology.objects.filter(port__host__address=self.target.target)
            if technologies.exists():
                c.drawString(100, y, "Identified Technologies:")
                y -= 20
                for tech in technologies:
                    c.drawString(120, y, f"- {tech.name} (Version: {tech.version or 'Unknown'})")
                    y -= 20
                    if y < 50:
                        c.showPage()
                        y = 750

            c.save()

            with open(report_path, 'rb') as f:
                self.report.save(f'{self.id}_report.pdf', File(f), save=True)

            logger.info(f"Report generated for Task ID {self.id}")
        except Exception as e:
            logger.error(f"Error generating report for Task ID {self.id}: {e}")