from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Sample, SampleTestResult, Label, TestResultDetail


class TestResultDetailInline(admin.StackedInline):
    model = TestResultDetail
    extra = 0


class SampleTestResultInline(admin.TabularInline):
    model = SampleTestResult
    extra = 0
    fields = ('test_date', 'quality_analysis', 'compliance_status', 'expiry_date', 'conducted_by')
    readonly_fields = ('test_date',)


class SampleAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'sample_type', 'sample_origin', 'testing_status', 'test_date', 'submitted_by')
    list_filter = ('testing_status', 'sample_type', 'test_date')
    search_fields = ('batch_number', 'sample_origin', 'metadata')
    readonly_fields = ('submitted_at',)
    inlines = [SampleTestResultInline]

    fieldsets = (
        (None, {
            'fields': ('batch_number', 'sample_type', 'sample_origin')
        }),
        ('Additional Information', {
            'fields': ('metadata', 'submitted_by', 'submitted_at')
        }),
        ('Status', {
            'fields': ('testing_status',)
        })
    )


class SampleTestResultAdmin(admin.ModelAdmin):
    list_display = ('sample', 'test_date', 'compliance_status', 'expiry_date', 'conducted_by')
    list_filter = ('compliance_status', 'test_date')
    search_fields = ('sample__batch_number', 'quality_analysis')
    readonly_fields = ('test_date',)
    inlines = [TestResultDetailInline]


class LabelAdmin(admin.ModelAdmin):
    list_display = ('certification_number', 'sample', 'generated_date', 'expiry_date', 'generated_by')
    list_filter = ('generated_date', 'expiry_date')
    search_fields = ('certification_number', 'sample__batch_number')
    readonly_fields = ('certification_number', 'generated_date', 'qr_code', 'pdf')

    fieldsets = (
        (None, {
            'fields': ('sample', 'expiry_date', 'generated_by')
        }),
        ('Generated Data', {
            'fields': ('certification_number', 'generated_date', 'qr_code', 'pdf')
        }),
    )


# Register models
admin.site.register(Sample, SampleAdmin)
admin.site.register(SampleTestResult, SampleTestResultAdmin)
admin.site.register(Label, LabelAdmin)