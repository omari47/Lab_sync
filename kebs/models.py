from django.db import models

# Create your models here.
from django.contrib.auth.models import User
from django.db import models
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils.timezone import now
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import uuid
import json
import os


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
        """Return the latest test result for this sample if any exists"""
        return self.test_results.order_by('-test_date').first()


class SampleTestResult(models.Model):
    COMPLIANCE_CHOICES = [
        (True, 'Compliant'),
        (False, 'Non-Compliant'),
    ]
    sample = models.ForeignKey(
        'Sample',
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
    label_data = models.JSONField()
    generated_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField()
    certification_number = models.CharField(max_length=50, unique=True)
    pdf = models.FileField(upload_to='labels/')
    qr_code = models.ImageField(
        upload_to='qr_codes/',
        blank=True,
        null=True
    )
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_labels'
    )

    def generate_qr(self):
        """Generate QR code containing a link to the test results PDF"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # Medium error correction for better scanning
            box_size=10,
            border=4,
        )

        # Create a URL that points to the test results PDF instead of the full certificate
        test_results_url = f"/sample-mis/test-results-pdf/{self.sample.sample_id}/"

        # We're using the test results URL as the primary data for direct access to results
        qr.add_data(test_results_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')

        # Save the QR code to the model
        filename = f'qr_{self.certification_number}.png'
        self.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)

    def generate_pdf(self):
        """Generate PDF certificate for this label"""
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, Table, TableStyle
        from reportlab.lib import colors
        import qrcode
        from io import BytesIO

        buffer = BytesIO()

        # Create the PDF object using ReportLab
        p = canvas.Canvas(buffer)

        # Generate QR code directly (even if we already have a saved image)
        qr_buffer = BytesIO()

        # Create a URL that points to the test results PDF
        test_results_url = f"/sample-mis/test-results-pdf/{self.sample.sample_id}/"

        # We'll use the test results URL for the QR code in the PDF certificate
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # Medium error correction for better scanning
            box_size=10,
            border=4,
        )

        # Use test results URL for direct access to simplified test results
        qr.add_data(test_results_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

        # PDF content
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 800, "KEBS CERTIFICATION LABEL")

        # Add QR code to the top right of the PDF
        p.drawImage(ImageReader(qr_buffer), 400, 700, width=150, height=150)

        p.setFont("Helvetica", 12)
        p.drawString(100, 750, f"Certification Number: {self.certification_number}")
        p.drawString(100, 730, f"Sample Batch: {self.sample.batch_number}")
        p.drawString(100, 710, f"Sample Type: {self.sample.get_sample_type_display()}")
        p.drawString(100, 690, f"Origin: {self.sample.sample_origin}")
        p.drawString(100, 670, f"Certification Date: {self.generated_date.strftime('%Y-%m-%d')}")
        p.drawString(100, 650, f"Expiry Date: {self.expiry_date.strftime('%Y-%m-%d')}")

        # Add footer note about the QR code
        p.drawString(400, 680, "Scan QR code for")
        p.drawString(400, 665, "test results")

        # Quality results summary
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 600, "Quality Analysis Summary")

        # Get latest test result
        latest_result = self.sample.latest_test_result()
        if latest_result:
            p.setFont("Helvetica", 10)

            # Break quality analysis text into lines to fit on PDF
            analysis_text = latest_result.quality_analysis
            text_obj = p.beginText(100, 580)
            for line in analysis_text.split('\n'):
                # Wrap long lines
                while line:
                    if len(line) <= 80:
                        text_obj.textLine(line)
                        line = ""
                    else:
                        text_obj.textLine(line[:80])
                        line = line[80:]

            p.drawText(text_obj)

            # Compliance statement
            p.setFont("Helvetica-Bold", 12)
            if latest_result.compliance_status:
                p.setFillColor(colors.green)
                p.drawString(100, 400, "COMPLIANT WITH KENYA STANDARDS")
            else:
                p.setFillColor(colors.red)
                p.drawString(100, 400, "NON-COMPLIANT WITH KENYA STANDARDS")

        # Reset color
        p.setFillColor(colors.black)

        # Add signature line
        p.line(100, 200, 300, 200)
        p.drawString(150, 180, "Authorized Signature")

        # Add official stamp placeholder
        p.circle(450, 190, 50)
        p.drawString(420, 190, "Official Stamp")

        # Add footer
        p.setFont("Helvetica-Oblique", 8)
        p.drawString(100, 50,
                     "This certificate is issued in accordance with the Kenya Bureau of Standards regulations.")
        p.drawString(100, 35, f"Verification code: {self.certification_number}")

        # Finalize the PDF
        p.showPage()
        p.save()

        # Save the PDF to the model
        filename = f'certificate_{self.certification_number}.pdf'
        buffer.seek(0)
        self.pdf.save(filename, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        # Generate certification number if not provided
        if not self.certification_number:
            self.certification_number = f"KEBS-{uuid.uuid4().hex[:8].upper()}"

        # Ensure generated_date is set before saving and generating PDF
        if not self.generated_date:
            from django.utils import timezone
            self.generated_date = timezone.now()

        if not self.label_data:
            # Create label data from sample information
            self.label_data = {
                'batch_number': self.sample.batch_number,
                'sample_type': self.sample.get_sample_type_display(),
                'origin': self.sample.sample_origin,
                'test_date': self.sample.test_date.strftime('%Y-%m-%d'),
                'expiry_date': self.expiry_date.strftime('%Y-%m-%d'),
                'generated_date': self.generated_date.strftime('%Y-%m-%d'),
            }

        # First save to ensure we have all fields populated
        generate_qr = not self.qr_code
        generate_pdf = not self.pdf

        # If this is a completely new label, save first
        if self.pk is None:
            super().save(*args, **kwargs)

        # Generate QR code and PDF after initial save
        if generate_qr:
            self.generate_qr()

        if generate_pdf:
            self.generate_pdf()

        # Save again if we generated new files
        super().save(*args, **kwargs)

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


# Signal to update sample status based on test results
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=SampleTestResult)
def update_sample_status(sender, instance, created, **kwargs):
    """
    Update the testing_status of the related Sample based on test results.
    IMPROVED: Only mark as 'Completed' when test results exist and are compliant
    """
    sample = instance.sample

    # Fetch all test results for this sample
    test_results = SampleTestResult.objects.filter(sample=sample)

    if test_results.exists():
        # Start by marking as "In Progress" when test results exist
        sample.testing_status = "In Progress"

        # Only mark as "Completed" if there's at least one test result and it's compliant
        # This ensures samples without test results or with non-compliant results don't get marked as completed
        compliant_results = test_results.filter(compliance_status=True)
        if compliant_results.exists():
            sample.testing_status = "Completed"
    else:
        # If no test results exist, ensure the sample is "Pending"
        sample.testing_status = "Pending"

    # Save the sample with the updated status
    sample.save(update_fields=['testing_status'])