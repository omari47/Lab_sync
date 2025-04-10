/**
 * Main JavaScript for KEBS MIS
 * Handles UI interactions and AJAX requests
 */

document.addEventListener('DOMContentLoaded', function() {
  // Setup search functionality
  setupSearch();

  // Setup label generation
  setupLabelGeneration();
});

/**
 * Fetch sample data via API
 * @param {string} query - Search query
 */
function fetchSampleData(query) {
  const url = `/sample-mis/api/samples/?q=${query}`;

  return fetch(url)
    .then(response => response.json())
    .catch(error => {
      console.error('Error fetching sample data:', error);
      return { samples: [] };
    });
}

/**
 * Display sample results in the container
 * @param {Array} samples - Sample data
 * @param {HTMLElement} container - Results container
 */
function displaySampleResults(samples, container) {
  if (samples.length === 0) {
    container.innerHTML = `
      <div class="text-center py-3">
        <i class="bi bi-search" style="font-size: 2rem; color: #ddd;"></i>
        <p class="text-muted mt-2">No samples found matching your search</p>
      </div>
    `;
    return;
  }

  let html = '<div class="list-group">';

  samples.forEach(sample => {
    const statusClass = getStatusClass(sample.status);
    const resultBadge = sample.latest_result
      ? `<span class="badge ${sample.latest_result.compliant ? 'badge-completed' : 'badge-non-compliant'} ms-2">
         ${sample.latest_result.compliant ? 'Compliant' : 'Non-Compliant'}
         </span>`
      : '';

    html += `
      <a href="/sample-mis/samples/${sample.id}/" class="list-group-item list-group-item-action">
        <div class="d-flex justify-content-between align-items-center">
          <h6 class="mb-0">${sample.batch_number}</h6>
          <span class="badge ${statusClass}">${sample.status}</span>
        </div>
        <small class="text-muted">
          ${sample.type} from ${sample.origin} (${formatDate(sample.date)})
          ${resultBadge}
        </small>
      </a>
    `;
  });

  html += '</div>';
  container.innerHTML = html;
}

/**
 * Generate label for a batch
 * @param {string} batchNumber - Batch number
 */
function generateLabel(batchNumber) {
  const url = "/sample-mis/generate-label/";
  const messageContainer = document.getElementById('label-message');

  // Show loading message
  messageContainer.innerHTML = '<div class="alert alert-info">Generating label...</div>';

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ batch_number: batchNumber })
  })
  .then(response => response.json())
  .then(data => {
    if (data.status === 'success') {
      messageContainer.innerHTML = `
        <div class="alert alert-success">${data.message}</div>
        <div class="card">
          <div class="card-body">
            <h5 class="card-title">Label Information</h5>
            <div class="detail-item">
              <div class="detail-label">Certification Number</div>
              <div>${data.certification_number}</div>
            </div>
            <div class="detail-item">
              <div class="detail-label">Generated Date</div>
              <div>${data.generated_date}</div>
            </div>
            <div class="detail-item">
              <div class="detail-label">Expiry Date</div>
              <div>${data.expiry_date}</div>
            </div>
            <div class="mt-3">
              <a href="/sample-mis/labels/${data.label_id}/download/" class="btn btn-primary" target="_blank">
                <i class="bi bi-download"></i> Download Certificate
              </a>
            </div>
          </div>
        </div>
      `;
    } else {
      messageContainer.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
    }
  })
  .catch(error => {
    console.error('Error generating label:', error);
    messageContainer.innerHTML = '<div class="alert alert-danger">Error generating label. Please try again.</div>';
  });
}

/**
 * Get appropriate CSS class for status badge
 * @param {string} status - Sample status
 * @returns {string} CSS class
 */
function getStatusClass(status) {
  switch (status) {
    case 'Pending':
      return 'badge-pending';
    case 'In Progress':
      return 'badge-in-progress';
    case 'Completed':
      return 'badge-completed';
    default:
      return 'badge-secondary';
  }
}

/**
 * Format date string
 * @param {string} dateString - Date string
 * @returns {string} Formatted date
 */
function formatDate(dateString) {
  const options = { year: 'numeric', month: 'short', day: 'numeric' };
  return new Date(dateString).toLocaleDateString(undefined, options);
}

/**
 * Get cookie by name (for CSRF token)
 * @param {string} name - Cookie name
 * @returns {string} Cookie value
 */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * Setup search functionality
 */
function setupSearch() {
  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');

  if (!searchInput || !searchResults) return;

  let debounceTimer;

  searchInput.addEventListener('input', function() {
    const query = this.value.trim();

    clearTimeout(debounceTimer);

    if (query.length === 0) {
      searchResults.innerHTML = '';
      return;
    }

    // Show loading indicator
    searchResults.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';

    debounceTimer = setTimeout(() => {
      fetchSampleData(query)
        .then(data => {
          displaySampleResults(data.samples, searchResults);
        });
    }, 300);
  });
}

/**
 * Setup label generation form
 */
function setupLabelGeneration() {
  const generateLabelBtns = document.querySelectorAll('.generate-label-btn');
  const labelModal = document.getElementById('labelModal');

  if (!generateLabelBtns.length || !labelModal) return;

  generateLabelBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      const batchNumber = this.getAttribute('data-batch');
      const bsModal = new bootstrap.Modal(labelModal);
      bsModal.show();
      generateLabel(batchNumber);
    });
  });
}