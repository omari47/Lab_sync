
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.urls import reverse, reverse_lazy
import json

from .models import Sample, SampleTestResult, Label, TestResultDetail
from .forms import SampleForm, SampleTestResultForm, LabelForm, SampleSearchForm, LoginForm, RegisterForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect('kebs:dashboard')

    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                next_url = request.GET.get('next')
                return redirect(next_url) if next_url else redirect('kebs:dashboard')
            messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid form submission.")
    else:
        form = LoginForm()

    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('kebs:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful. Welcome to KEBS Sample MIS!")
            return redirect('kebs:dashboard')
        messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = RegisterForm()

    return render(request, 'auth/register.html', {'form': form})


@login_required
def dashboard(request):
    pending_count = Sample.objects.filter(testing_status='Pending').count()
    in_progress_count = Sample.objects.filter(testing_status='In Progress').count()
    completed_count = Sample.objects.filter(testing_status='Completed').count()

    sample_types = Sample.objects.values('sample_type').annotate(count=Count('sample_id')).order_by('-count')
    recent_samples = Sample.objects.all().order_by('-submitted_at')[:5]
    recent_results = SampleTestResult.objects.all().order_by('-test_date')[:5]
    
    current_year = timezone.now().year
    monthly_data = []
    for month in range(1, 13):
        count = Sample.objects.filter(submitted_at__year=current_year, submitted_at__month=month).count()
        monthly_data.append(count)

    context = {
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'total_count': pending_count + in_progress_count + completed_count,
        'sample_types': sample_types,
        'recent_samples': recent_samples,
        'recent_results': recent_results,
        'monthly_data': monthly_data,
        'user': request.user,
    }
    return render(request, 'dashboard.html', context)


@login_required
def sample_list(request):
    samples = Sample.objects.all()

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    if search_query:
        samples = samples.filter(
            Q(batch_number__icontains=search_query) |
            Q(sample_origin__icontains=search_query) |
            Q(metadata__icontains=search_query)
        )

    if status_filter:
        samples = samples.filter(testing_status=status_filter)
    if type_filter:
        samples = samples.filter(sample_type=type_filter)

    samples = samples.order_by('-submitted_at')
    paginator = Paginator(samples, 10)
    page_number = request.GET.get('page', 1)
    samples_page = paginator.get_page(page_number)

    context = {
        'samples': samples_page,
        'search_query': search_query,
        'status_filter': status_filter,
        'type_filter': type_filter,
    }
    return render(request, 'samples/sample_list.html', context)


@login_required
def sample_detail(request, sample_id):
    sample = get_object_or_404(Sample, sample_id=sample_id)
    test_results = sample.test_results.all().order_by('-test_date')
    try:
        label = sample.label
    except Label.DoesNotExist:
        label = None

    context = {
        'sample': sample,
        'test_results': test_results,
        'label': label,
    }
    return render(request, 'samples/sample_detail.html', context)


@login_required
def add_test_result(request, sample_id):
    sample = get_object_or_404(Sample, sample_id=sample_id)
    if request.method == 'POST':
        form = SampleTestResultForm(request.POST)
        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.sample = sample
            test_result.conducted_by = request.user
            try:
                test_result.save()
            except Exception as e:
                messages.error(request, f"Error adding test result: {e}")
                return redirect('kebs:sample_detail', sample_id=sample.sample_id)

            messages.success(request, 'Test result added successfully.')
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleTestResultForm()

    return render(request, 'samples/add_test_result.html', {'sample': sample, 'form': form})


@login_required
def generate_label(request):
    """
    AJAX endpoint to generate a label based on a sample's batch number.
    Expects a JSON payload: { "batch_number": "<batch_number>" }
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        batch_number = data.get('batch_number')
        if not batch_number:
            raise ValueError("Batch number missing")
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'status': 'error', 'message': f'Invalid JSON data: {e}'}, status=400)

    try:
        sample = Sample.objects.get(batch_number=batch_number)
    except Sample.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Sample not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error retrieving sample: {e}'}, status=500)

    latest_result = sample.latest_test_result()
    if not latest_result:
        return JsonResponse({'status': 'error', 'message': 'No test results found for this sample'}, status=400)

    if not latest_result.compliance_status:
        return JsonResponse({'status': 'error', 'message': 'Sample is not compliant, cannot generate label'}, status=400)

    # Retrieve an existing label or create a new one.
    label_exists = False
    try:
        label = sample.label
        label_exists = True
        # Regenerate files if missing.
        if not label.qr_code or not label.pdf:
            if not label.qr_code:
                label.generate_qr()  # Optionally, call and save the result
            if not label.pdf:
                label.generate_pdf()
            label.save()
    except Label.DoesNotExist:
        label_data = {
            'batch_number': sample.batch_number,
            'sample_type': sample.get_sample_type_display(),
            'origin': sample.sample_origin,
            'test_date': sample.test_date.strftime('%Y-%m-%d'),
            'expiry_date': latest_result.expiry_date.date().strftime('%Y-%m-%d'),
        }
        try:
            label = Label(
                sample=sample,
                expiry_date=latest_result.expiry_date.date(),
                generated_by=request.user,
                generated_date=timezone.now(),
                label_data=label_data,
            )
            label.save()
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error creating label: {e}'}, status=500)

    response_data = {
        'status': 'success',
        'message': 'Label generated successfully' if not label_exists else 'Label already exists',
        'label_id': label.id,
        'certification_number': label.certification_number,
        'generated_date': label.generated_date.strftime('%Y-%m-%d'),
        'expiry_date': label.expiry_date.strftime('%Y-%m-%d'),
    }
    return JsonResponse(response_data)


@login_required
def download_label(request, label_id):
    label = get_object_or_404(Label, id=label_id)
    try:
        filename = f'KEBS_Certificate_{label.certification_number}.pdf'
        response = FileResponse(open(label.pdf.path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except FileNotFoundError:
        raise Http404("Label PDF not found")


@login_required
def view_test_results_pdf(request, sample_id):
    sample = get_object_or_404(Sample, sample_id=sample_id)
    test_result = sample.latest_test_result()
    if not test_result:
        raise Http404("No test results found for this sample")

    # Generate PDF using ReportLab
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from io import BytesIO

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    p.setFont("Helvetica-Bold", 16)
    p.drawString(1 * inch, height - 1 * inch, "KEBS TEST RESULTS SUMMARY")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(1 * inch, height - 1.5 * inch, "Sample Information:")

    p.setFont("Helvetica", 10)
    p.drawString(1 * inch, height - 1.8 * inch, f"Batch Number: {sample.batch_number}")
    p.drawString(1 * inch, height - 2.1 * inch, f"Sample Type: {sample.get_sample_type_display()}")
    p.drawString(1 * inch, height - 2.4 * inch, f"Origin: {sample.sample_origin}")
    p.drawString(1 * inch, height - 2.7 * inch, f"Test Date: {test_result.test_date.strftime('%Y-%m-%d')}")

    p.setFont("Helvetica-Bold", 14)
    if test_result.compliance_status:
        p.setFillColor(colors.green)
        p.drawString(1 * inch, height - 3.3 * inch, "COMPLIANT WITH KENYA STANDARDS")
    else:
        p.setFillColor(colors.red)
        p.drawString(1 * inch, height - 3.3 * inch, "NON-COMPLIANT WITH KENYA STANDARDS")
    p.setFillColor(colors.black)

    p.setFont("Helvetica-Bold", 12)
    p.drawString(1 * inch, height - 4 * inch, "Test Results:")
    p.setFont("Helvetica", 10)
    analysis_text = test_result.quality_analysis
    text_obj = p.beginText(1 * inch, height - 4.3 * inch)
    for line in analysis_text.split('\n'):
        while line:
            if len(line) <= 80:
                text_obj.textLine(line)
                line = ""
            else:
                text_obj.textLine(line[:80])
                line = line[80:]
    p.drawText(text_obj)

    p.setFont("Helvetica-Italic", 8)
    p.drawString(1 * inch, 1 * inch, f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    p.drawString(1 * inch, 0.75 * inch,
                 "This document is a summary of test results. For the full certificate, please contact KEBS.")
    p.showPage()
    p.save()
    buffer.seek(0)
    response = FileResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="TestResults_{sample.batch_number}.pdf"'
    return response


@login_required
def api_sample_list(request):
    query = request.GET.get('q', '')
    samples = Sample.objects.all()
    if query:
        samples = samples.filter(
            Q(batch_number__icontains=query) |
            Q(sample_origin__icontains=query) |
            Q(metadata__icontains=query)
        )
    samples = samples.order_by('-submitted_at')[:20]

    data = []
    for sample in samples:
        latest_result = sample.latest_test_result()
        result_data = None
        if latest_result:
            result_data = {
                'date': latest_result.test_date.strftime('%Y-%m-%d'),
                'compliant': latest_result.compliance_status,
            }
        sample_data = {
            'id': sample.sample_id,
            'batch_number': sample.batch_number,
            'type': sample.get_sample_type_display(),
            'origin': sample.sample_origin,
            'status': sample.testing_status,
            'date': sample.submitted_at.strftime('%Y-%m-%d'),
            'latest_result': result_data,
        }
        data.append(sample_data)

    return JsonResponse({'samples': data})


@login_required
def add_test_result_crispy(request, sample_id):
    sample = get_object_or_404(Sample, sample_id=sample_id)
    if request.method == 'POST':
        form = SampleTestResultForm(request.POST)
        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.sample = sample
            test_result.conducted_by = request.user
            try:
                test_result.save()
            except Exception as e:
                messages.error(request, f"Error saving test result: {e}")
                return redirect('kebs:sample_detail', sample_id=sample.sample_id)
            sample.testing_status = 'Completed'
            sample.save()
            messages.success(request, 'Test result added successfully.')
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleTestResultForm()

    return render(request, 'samples/add_test_result_crispy.html', {'sample': sample, 'form': form})


@login_required
def data_management(request):
    samples = Sample.objects.all().order_by('-submitted_at')[:20]
    test_results = SampleTestResult.objects.all().order_by('-test_date')[:20]
    labels = Label.objects.all().order_by('-generated_date')[:20]
    context = {
        'samples': samples,
        'test_results': test_results,
        'labels': labels
    }
    return render(request, 'data_management_new.html', context)


@login_required
def create_sample(request):
    if request.method == 'POST':
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.submitted_by = request.user
            try:
                sample.save()
            except Exception as e:
                messages.error(request, f"Error creating sample: {e}")
                return render(request, 'samples/create_sample.html', {'form': form})
            messages.success(request, "Sample created successfully.")
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleForm()

    return render(request, 'samples/create_sample.html', {'form': form})


@login_required
def sample_tracking(request):
    return render(request, 'samples/sample_tracking.html')

from django.http import JsonResponse
from .models import Sample
from django.db.models import Q
from django.http import JsonResponse
from .models import Sample

def api_samples(request):
    query = request.GET.get("q", "").strip()
    samples = Sample.objects.all()

    if query:
        samples = samples.filter(
            Q(sample_id__icontains=query) |
            Q(batch_number__icontains=query)
        )

    data = {
        "samples": [
            {
                # If 'sample_id' is the unique field you use in your URLs:
                "id": sample.sample_id,  # Or just sample.id if you prefer the default PK
                # If you have a method for displaying sample_type:
                "type": sample.get_sample_type_display(),  
                "batch_number": sample.batch_number,
                # Change from sample.status to the correct field, e.g.:
                "status": sample.testing_status,
                # Change from sample.created_at to the correct date field, e.g.:
                "date": sample.submitted_at.strftime("%Y-%m-%d"),
            }
            for sample in samples
        ]
    }
    return JsonResponse(data)


@login_required
def test_results(request):
    results = SampleTestResult.objects.all().order_by('-test_date')
    search_query = request.GET.get('q', '')
    if search_query:
        results = results.filter(
            Q(sample__batch_number__icontains=search_query) |
            Q(sample__sample_id__icontains=search_query) |
            Q(quality_analysis__icontains=search_query)
        )
    paginator = Paginator(results, 10)
    page_number = request.GET.get('page', 1)
    results_page = paginator.get_page(page_number)
    return render(request, 'samples/test_results.html', {'results': results_page, 'search_query': search_query})


@login_required
def test_results_detail(request, sample_id):
    sample = get_object_or_404(Sample, sample_id=sample_id)
    test_result = sample.test_results.order_by('-test_date').first()
    if not test_result:
        messages.warning(request, f"No test results found for Sample #{sample_id}")
        return redirect('kebs:sample_detail', sample_id=sample_id)
    try:
        detail = test_result.detail
    except TestResultDetail.DoesNotExist:
        detail = None
    context = {
        'sample': sample,
        'test_result': test_result,
        'detail': detail,
    }
    return render(request, 'samples/test_results_detail.html', context)


@login_required
def generate_label_page(request):
    return render(request, 'samples/generate_label.html')



@login_required
def api_generate_label(request):
    query = request.GET.get('query', '')
    if not query:
        return JsonResponse({'error': 'No sample ID or batch number provided'}, status=400)
    try:
        sample = Sample.objects.filter(batch_number=query).first()
        if not sample and query.isdigit():
            sample = Sample.objects.filter(sample_id=int(query)).first()
        if not sample:
            return JsonResponse({'error': 'Sample not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Error retrieving sample: {e}'}, status=500)

    latest_result = sample.latest_test_result()
    if not latest_result:
        return JsonResponse({'error': 'No test results found for this sample'}, status=400)
    if not latest_result.compliance_status:
        return JsonResponse({'error': 'Sample is not compliant, cannot generate label'}, status=400)

    try:
        label = sample.label
        if not label.qr_code or not label.pdf:
            # Optionally trigger regeneration of files if missing.
            if not label.qr_code:
                label.generate_qr()
            if not label.pdf:
                label.generate_pdf()
            label.save()
    except Label.DoesNotExist:
        try:
            label = Label(
                sample=sample,
                expiry_date=latest_result.expiry_date.date(),
                generated_by=request.user if request.user.is_authenticated else None
            )
            label.save()
        except Exception as save_error:
            print(f"Error saving label: {save_error}")
            return JsonResponse({'error': f'Error generating label: {save_error}'}, status=500)

    if not label.qr_code:
        return JsonResponse({'error': 'QR code generation failed'}, status=500)
    if not label.pdf:
        return JsonResponse({'error': 'PDF generation failed'}, status=500)

    try:
        qr_code_url = label.qr_code.url if label.qr_code else None
        pdf_url = label.pdf.url if label.pdf else None
    except Exception as url_error:
        print(f"Error getting media URLs: {url_error}")
        return JsonResponse({'error': f'Error with media files: {url_error}'}, status=500)

    return JsonResponse({
        'sample_id': sample.sample_id,
        'batch_number': sample.batch_number,
        'expiry_date': label.expiry_date.strftime('%Y-%m-%d'),
        'certification_number': label.certification_number,
        'generated_date': label.generated_date.strftime('%Y-%m-%d'),
        'label_id': label.id,
        'qr_code_url': qr_code_url,
        'pdf_url': pdf_url,
    })
