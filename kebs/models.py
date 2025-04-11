
from django.db import models
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils.timezone import now
import qrcode
from io import BytesIO
import uuid
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors


class Sample(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]
    TYPE_CHOICES = [
        ('Food', 'Food'),
        ('Chemical', 'Chemical'),
        ('Textile', 'Textile'),
        ('Other', 'Other'),
    ]

    sample_id = models.AutoField(primary_key=True)
    sample_type = models.CharField(max_length=100, choices=TYPE_CHOICES)
    sample_origin = models.CharField(max_length=100)
    batch_number = models.CharField(max_length=50, unique=True)
    testing_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    test_date = models.DateField(auto_now_add=True)
    metadata = models.TextField(blank=True, null=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_samples'
    )
    submitted_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ['-test_date', '-sample_id']
        verbose_name = "Sample"
        verbose_name_plural = "Samples"

    def __str__(self):
        return f"{self.batch_number} ({self.get_sample_type_display()})"

    def latest_test_result(self):
        return self.test_results.order_by('-test_date').first()


class SampleTestResult(models.Model):
    COMPLIANCE_CHOICES = [
        (True, 'Compliant'),
        (False, 'Non-Compliant'),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name='test_results'
    )
    quality_analysis = models.TextField()
    compliance_status = models.BooleanField(choices=COMPLIANCE_CHOICES, default=False)
    test_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    conducted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conducted_tests'
    )

    class Meta:
        ordering = ['-test_date']
        verbose_name = "Sample Test Result"
        verbose_name_plural = "Sample Test Results"

    def __str__(self):
        status = "Compliant" if self.compliance_status else "Non-Compliant"
        return f"Result for {self.sample.batch_number} ({status})"


class Label(models.Model):
    sample = models.OneToOneField(
        Sample,
        on_delete=models.CASCADE,
        related_name='label'
    )
    label_data = models.JSONField(default=dict)
    generated_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField()
    certification_number = models.CharField(max_length=50, unique=True)
    pdf = models.FileField(upload_to='labels/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_labels'
    )

    def generate_qr(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        url = f"/kebs/test-results-pdf/{self.sample.sample_id}/"
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        filename = f'qr_{self.certification_number}.png'
        self.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)

    def generate_pdf(self):
        buffer = BytesIO()
        p = canvas.Canvas(buffer)

        # Generate QR code image
        qr_buffer = BytesIO()
        url = f"/kebs/test-results-pdf/{self.sample.sample_id}/"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

        # Draw certificate content
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 800, "KEBS CERTIFICATION LABEL")
        p.drawImage(ImageReader(qr_buffer), 400, 700, width=150, height=150)

        p.setFont("Helvetica", 12)
        p.drawString(100, 750, f"Certification Number: {self.certification_number}")
        p.drawString(100, 730, f"Sample Batch: {self.sample.batch_number}")
        p.drawString(100, 710, f"Sample Type: {self.sample.get_sample_type_display()}")
        p.drawString(100, 690, f"Origin: {self.sample.sample_origin}")
        p.drawString(100, 670, f"Certification Date: {self.generated_date.strftime('%Y-%m-%d')}")
        p.drawString(100, 650, f"Expiry Date: {self.expiry_date.strftime('%Y-%m-%d')}")
        p.drawString(400, 680, "Scan QR code for")
        p.drawString(400, 665, "test results")

        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 600, "Quality Analysis Summary")

        result = self.sample.latest_test_result()
        if result:
            p.setFont("Helvetica", 10)
            text_obj = p.beginText(100, 580)
            for line in result.quality_analysis.split('\n'):
                while line:
                    text_obj.textLine(line[:80])
                    line = line[80:]
            p.drawText(text_obj)

            p.setFont("Helvetica-Bold", 12)
            if result.compliance_status:
                p.setFillColor(colors.green)
                p.drawString(100, 400, "COMPLIANT WITH KENYA STANDARDS")
            else:
                p.setFillColor(colors.red)
                p.drawString(100, 400, "NON-COMPLIANT WITH KENYA STANDARDS")

        p.setFillColor(colors.black)
        p.line(100, 200, 300, 200)
        p.drawString(150, 180, "Authorized Signature")
        p.circle(450, 190, 50)
        p.drawString(420, 190, "Official Stamp")

        p.setFont("Helvetica-Oblique", 8)
        p.drawString(100, 50, "This certificate is issued in accordance with the Kenya Bureau of Standards regulations.")
        p.drawString(100, 35, f"Verification code: {self.certification_number}")

        p.showPage()
        p.save()

        buffer.seek(0)
        filename = f'certificate_{self.certification_number}.pdf'
        self.pdf.save(filename, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        creating = self.pk is None

        if not self.certification_number:
            self.certification_number = f"KEBS-{uuid.uuid4().hex[:8].upper()}"
        if not self.generated_date:
            self.generated_date = now()
        if not self.label_data and self.sample:
            self.label_data = {
                'batch_number': self.sample.batch_number,
                'sample_type': self.sample.get_sample_type_display(),
                'origin': self.sample.sample_origin,
                'test_date': self.sample.test_date.strftime('%Y-%m-%d'),
                'expiry_date': self.expiry_date.strftime('%Y-%m-%d'),
                'generated_date': self.generated_date.strftime('%Y-%m-%d'),
            }

        super().save(*args, **kwargs)

        updated = False
        if not self.qr_code:
            self.generate_qr()
            updated = True
        if not self.pdf:
            self.generate_pdf()
            updated = True
        if updated:
            super().save(update_fields=['qr_code', 'pdf'])

    def __str__(self):
        return f"Label for {self.sample.batch_number}"


class TestResultDetail(models.Model):
    test_result = models.OneToOneField(
        SampleTestResult,
        on_delete=models.CASCADE,
        related_name='detail'
    )
    parameters = models.JSONField(blank=True, null=True)
    additional_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Details for {self.test_result}"


# --- SIGNAL: Update Sample Status after Test Result Save ---
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=SampleTestResult)
def update_sample_status(sender, instance, created, **kwargs):
    sample = instance.sample
    results = sample.test_results.all()

    if results.exists():
        sample.testing_status = "In Progress"
        if results.filter(compliance_status=True).exists():
            sample.testing_status = "Completed"
    else:
        sample.testing_status = "Pending"

    sample.save(update_fields=['testing_status'])
