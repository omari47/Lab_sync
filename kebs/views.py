from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse_lazy, reverse
import json

from .models import Sample, SampleTestResult, Label, TestResultDetail
from .forms import SampleForm, SampleTestResultForm, LabelForm, SampleSearchForm, LoginForm, RegisterForm


def login_view(request):
    """
    User login view
    """
    if request.user.is_authenticated:
        return redirect('kebs:dashboard')

    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # Redirect to the page user was trying to access if specified in next parameter
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('kebs:dashboard')
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid form submission.")
    else:
        form = LoginForm()

    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    """
    User logout view
    """
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('login')


def register_view(request):
    """
    User registration view
    """
    if request.user.is_authenticated:
        return redirect('kebs:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful. Welcome to KEBS Sample MIS!")
            return redirect('kebs:dashboard')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = RegisterForm()

    return render(request, 'auth/register.html', {'form': form})


@login_required
def dashboard(request):
    """
    Main dashboard view showing key statistics and recent samples.
    Requires login to access.
    """
    # Get counts for each status
    pending_count = Sample.objects.filter(testing_status='Pending').count()
    in_progress_count = Sample.objects.filter(testing_status='In Progress').count()
    completed_count = Sample.objects.filter(testing_status='Completed').count()

    # Get counts by sample type
    sample_types = Sample.objects.values('sample_type').annotate(
        count=Count('sample_id')).order_by('-count')

    # Recent samples
    recent_samples = Sample.objects.all().order_by('-submitted_at')[:5]

    # Recent test results
    recent_results = SampleTestResult.objects.all().order_by('-test_date')[:5]

    # Monthly submissions (for chart)
    current_year = timezone.now().year
    monthly_data = []

    for month in range(1, 13):
        count = Sample.objects.filter(
            submitted_at__year=current_year,
            submitted_at__month=month
        ).count()
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
        'user': request.user  # Pass the user to the template
    }

    return render(request, 'dashboard.html', context)


@login_required
def sample_list(request):
    """
    List all samples with filtering options.
    Requires login to access.
    """
    samples = Sample.objects.all()

    # Get filter parameters from request
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    # Apply filters
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

    # Order samples
    samples = samples.order_by('-submitted_at')

    # Pagination
    paginator = Paginator(samples, 10)  # Show 10 samples per page
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
    """
    View details of a specific sample.
    Requires login to access.
    """
    sample = get_object_or_404(Sample, sample_id=sample_id)

    # Get test results for this sample
    test_results = sample.test_results.all().order_by('-test_date')

    # Check if a label exists
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
    """
    Add a test result to a sample
    """
    sample = get_object_or_404(Sample, sample_id=sample_id)

    if request.method == 'POST':
        form = SampleTestResultForm(request.POST)

        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.sample = sample
            test_result.conducted_by = request.user
            test_result.save()

            messages.success(request, 'Test result added successfully.')
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleTestResultForm()

    context = {
        'sample': sample,
        'form': form,
    }

    return render(request, 'samples/add_test_result.html', context)


@login_required
def generate_label(request):
    """
    Generate a label for a sample (AJAX endpoint)
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        batch_number = data.get('batch_number')

        try:
            sample = Sample.objects.get(batch_number=batch_number)

            # Check if sample has test results and is compliant
            latest_result = sample.latest_test_result()
            if not latest_result:
                return JsonResponse({'status': 'error', 'message': 'No test results found for this sample'})

            if not latest_result.compliance_status:
                return JsonResponse({'status': 'error', 'message': 'Sample is not compliant, cannot generate label'})

            # Check if label already exists
            try:
                label = sample.label
                label_exists = True
            except Label.DoesNotExist:
                # Create new label with all required data
                label = Label(
                    sample=sample,
                    expiry_date=latest_result.expiry_date.date(),
                    generated_by=request.user,
                    generated_date=timezone.now(),  # Set the generated date explicitly
                    label_data={  # Pre-populate label data
                        'batch_number': sample.batch_number,
                        'sample_type': sample.get_sample_type_display(),
                        'origin': sample.sample_origin,
                        'test_date': sample.test_date.strftime('%Y-%m-%d'),
                        'expiry_date': latest_result.expiry_date.date().strftime('%Y-%m-%d'),
                    }
                )
                try:
                    label.save()
                    label_exists = False
                except Exception as e:
                    print(f"Error saving label: {str(e)}")
                    return JsonResponse({'status': 'error', 'message': f'Error creating label: {str(e)}'})

            # Return success response with label info
            return JsonResponse({
                'status': 'success',
                'message': 'Label generated successfully' if not label_exists else 'Label already exists',
                'label_id': label.id,
                'certification_number': label.certification_number,
                'generated_date': label.generated_date.strftime('%Y-%m-%d'),
                'expiry_date': label.expiry_date.strftime('%Y-%m-%d'),
            })

        except Sample.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Sample not found'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@login_required
def download_label(request, label_id):
    """
    Download a label PDF with forced download
    """
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
    """
    Generate and view a simplified test results PDF with just test results and compliance status
    """
    sample = get_object_or_404(Sample, sample_id=sample_id)
    test_result = sample.latest_test_result()

    if not test_result:
        raise Http404("No test results found for this sample")

    # Create a PDF with test results
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from io import BytesIO
    from django.utils import timezone

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Add title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(1 * inch, height - 1 * inch, "KEBS TEST RESULTS SUMMARY")

    # Add sample details
    p.setFont("Helvetica-Bold", 12)
    p.drawString(1 * inch, height - 1.5 * inch, "Sample Information:")

    p.setFont("Helvetica", 10)
    p.drawString(1 * inch, height - 1.8 * inch, f"Batch Number: {sample.batch_number}")
    p.drawString(1 * inch, height - 2.1 * inch, f"Sample Type: {sample.get_sample_type_display()}")
    p.drawString(1 * inch, height - 2.4 * inch, f"Origin: {sample.sample_origin}")
    p.drawString(1 * inch, height - 2.7 * inch, f"Test Date: {test_result.test_date.strftime('%Y-%m-%d')}")

    # Add compliance status with color
    p.setFont("Helvetica-Bold", 14)
    if test_result.compliance_status:
        p.setFillColor(colors.green)
        p.drawString(1 * inch, height - 3.3 * inch, "COMPLIANT WITH KENYA STANDARDS")
    else:
        p.setFillColor(colors.red)
        p.drawString(1 * inch, height - 3.3 * inch, "NON-COMPLIANT WITH KENYA STANDARDS")

    # Reset color for the rest of the content
    p.setFillColor(colors.black)

    # Add test results
    p.setFont("Helvetica-Bold", 12)
    p.drawString(1 * inch, height - 4 * inch, "Test Results:")

    # Quality analysis text
    p.setFont("Helvetica", 10)

    # Break quality analysis text into lines to fit on PDF
    analysis_text = test_result.quality_analysis
    text_obj = p.beginText(1 * inch, height - 4.3 * inch)
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

    # Add footer
    p.setFont("Helvetica-Italic", 8)
    p.drawString(1 * inch, 1 * inch, f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    p.drawString(1 * inch, 0.75 * inch,
                 "This document is a summary of test results. For the full certificate, please contact KEBS.")

    # Finalize the PDF
    p.showPage()
    p.save()
    buffer.seek(0)

    # Return the PDF
    response = FileResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="TestResults_{sample.batch_number}.pdf"'

    return response


@login_required
def api_sample_list(request):
    """
    API endpoint for returning sample data.
    Requires login to access.
    """
    query = request.GET.get('q', '')

    samples = Sample.objects.all()

    if query:
        samples = samples.filter(
            Q(batch_number__icontains=query) |
            Q(sample_origin__icontains=query) |
            Q(metadata__icontains=query)
        )

    samples = samples.order_by('-submitted_at')[:20]  # Limit to 20 results

    data = []
    for sample in samples:
        # Get latest test result if available
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
    """
    Add a test result to a sample using crispy forms
    """
    sample = get_object_or_404(Sample, sample_id=sample_id)

    if request.method == 'POST':
        form = SampleTestResultForm(request.POST)

        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.sample = sample
            test_result.conducted_by = request.user
            test_result.save()

            # Update sample status to completed since test results exist
            sample.testing_status = 'Completed'
            sample.save()

            messages.success(request, 'Test result added successfully.')
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleTestResultForm()

    context = {
        'sample': sample,
        'form': form,
    }

    return render(request, 'samples/add_test_result_crispy.html', context)


@login_required
def data_management(request):
    """
    Data management center with tabs for different data types.
    Requires login to access.
    """
    # Get samples, test results, and labels for display
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
    """
    Create a new sample entry.
    Requires login to access.
    """
    if request.method == 'POST':
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.submitted_by = request.user
            sample.save()
            messages.success(request, "Sample created successfully.")
            return redirect('kebs:sample_detail', sample_id=sample.sample_id)
    else:
        form = SampleForm()

    return render(request, 'samples/create_sample.html', {'form': form})


@login_required
def sample_tracking(request):
    """
    Sample tracking page with search functionality.
    Requires login to access.
    """
    return render(request, 'samples/sample_tracking.html')


@login_required
def test_results(request):
    """
    View for listing all test results with filtering.
    Requires login to access.
    """
    results = SampleTestResult.objects.all().order_by('-test_date')

    # Get search query parameter
    search_query = request.GET.get('q', '')

    # Apply search filter if provided
    if search_query:
        results = results.filter(
            Q(sample__batch_number__icontains=search_query) |
            Q(sample__sample_id__icontains=search_query) |
            Q(quality_analysis__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(results, 10)  # Show 10 results per page
    page_number = request.GET.get('page', 1)
    results_page = paginator.get_page(page_number)

    context = {
        'results': results_page,
        'search_query': search_query,
    }

    return render(request, 'samples/test_results.html', context)


@login_required
def test_results_detail(request, sample_id):
    """
    Detailed view of test results for a specific sample.
    Requires login to access.
    """
    sample = get_object_or_404(Sample, sample_id=sample_id)

    # Get the latest test result
    test_result = sample.test_results.order_by('-test_date').first()

    if not test_result:
        messages.warning(request, f"No test results found for Sample #{sample_id}")
        return redirect('kebs:sample_detail', sample_id=sample_id)

    # Try to get test result details if they exist
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
    """
    Page for generating labels with UI
    """
    return render(request, 'samples/generate_label.html')


@login_required
def api_generate_label(request):
    """
    API endpoint for generating a label from the UI
    """
    query = request.GET.get('query', '')

    if not query:
        return JsonResponse({'error': 'No sample ID or batch number provided'}, status=400)

    # Try to find the sample by batch number or ID
    try:
        # First try by batch number (exact match)
        sample = Sample.objects.filter(batch_number=query).first()

        # If not found, try by sample ID
        if not sample and query.isdigit():
            sample = Sample.objects.filter(sample_id=int(query)).first()

        if not sample:
            return JsonResponse({'error': 'Sample not found'}, status=404)

        # Check if sample has test results and is compliant
        latest_result = sample.latest_test_result()
        if not latest_result:
            return JsonResponse({'error': 'No test results found for this sample'}, status=400)

        if not latest_result.compliance_status:
            return JsonResponse({'error': 'Sample is not compliant, cannot generate label'}, status=400)

        # Check if label already exists
        try:
            label = sample.label
            # Force regenerate QR code and PDF if needed
            if not label.qr_code or not label.pdf:
                if not label.qr_code:
                    label.generate_qr()
                if not label.pdf:
                    label.generate_pdf()
                label.save()
        except Label.DoesNotExist:
            # Create new label if it doesn't exist
            label = Label(
                sample=sample,
                expiry_date=latest_result.expiry_date.date(),
                generated_by=request.user if request.user.is_authenticated else None
            )
            try:
                label.save()
            except Exception as save_error:
                print(f"Error saving label: {str(save_error)}")
                return JsonResponse({'error': f'Error generating label: {str(save_error)}'}, status=500)

        # Verify QR code and PDF were generated
        if not label.qr_code:
            return JsonResponse({'error': 'QR code generation failed'}, status=500)

        if not label.pdf:
            return JsonResponse({'error': 'PDF generation failed'}, status=500)

        # Get QR code URL if available
        try:
            qr_code_url = label.qr_code.url if label.qr_code else None
            pdf_url = label.pdf.url if label.pdf else None
        except Exception as url_error:
            print(f"Error getting media URLs: {str(url_error)}")
            return JsonResponse({'error': f'Error with media files: {str(url_error)}'}, status=500)

        # Return label data
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

    except Exception as e:
        import traceback
        print(f"Label generation error: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)