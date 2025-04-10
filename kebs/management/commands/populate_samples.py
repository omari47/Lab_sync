from django.core.management.base import BaseCommand
from kebs.models import Sample, SampleTestResult, TestResultDetail, Label
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker
import random
from datetime import timedelta

fake = Faker()

class Command(BaseCommand):
    help = 'Populate the database with sample data'

    def handle(self, *args, **kwargs):
        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR("No users found. Please create a superuser first."))
            return

        sample_types = ['Food', 'Chemical', 'Textile', 'Other']
        statuses = [True, False]

        for i in range(50):
            batch_number = f"BATCH-{fake.unique.bothify(text='???###')}"
            sample = Sample.objects.create(
                sample_type=random.choice(sample_types),
                sample_origin=fake.city(),
                batch_number=batch_number,
                submitted_by=user
            )

            # Add a test result
            compliant = random.choice(statuses)
            result = SampleTestResult.objects.create(
                sample=sample,
                quality_analysis=fake.paragraph(nb_sentences=3),
                compliance_status=compliant,
                expiry_date=timezone.now() + timedelta(days=random.randint(100, 365)),
                conducted_by=user
            )

            # Add result details
            TestResultDetail.objects.create(
                test_result=result,
                parameters={
                    "pH": round(random.uniform(6.0, 8.0), 2),
                    "Lead": round(random.uniform(0.0, 0.05), 3),
                    "Microbial Load": random.choice(["Low", "Moderate", "High"])
                },
                additional_notes=fake.sentence()
            )

            # Create label properly (let model generate the QR and PDF)
            label = Label(
                sample=sample,
                expiry_date=timezone.now().date() + timedelta(days=random.randint(100, 365)),
                generated_by=user
            )
            label.save()  # Triggers QR and PDF generation internally

            self.stdout.write(self.style.SUCCESS(f"Created sample: {batch_number}"))

        self.stdout.write(self.style.SUCCESS("✅ Successfully populated 50 samples."))
