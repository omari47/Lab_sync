/**
 * Label Generation Utility Functions
 */

/**
 * Generate a label for a sample based on batch number
 * @param {string} batchNumber - The batch number of the sample
 * @returns {Promise} - Promise that resolves when label is generated
 */
function generateLabel(batchNumber) {
    return new Promise((resolve, reject) => {
        if (!batchNumber) {
            reject(new Error('Batch number is required'));
            return;
        }

        // CSRF token for POST requests
        const csrftoken = getCookie('csrftoken');

        // Make POST request to generate label
        fetch('/kebs/generate-label/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ batch_number: batchNumber }),
            credentials: 'same-origin',  // This ensures cookies are sent with the request
            redirect: 'follow'          // This allows the browser to follow redirects
        })
        .then(response => {
            // Check if we were redirected to login page
            if (response.redirected && response.url.includes('login')) {
                // User is not authenticated, redirect to login page
                window.location.href = response.url;
                throw new Error('Authentication required');
            }

            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.message || 'Error generating label');
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                // Create success message with download link
                let messageHTML = `
                    <div class="alert alert-success">
                        <h5><i class="bi bi-check-circle"></i> Label Generated Successfully</h5>
                        <p>Certification Number: <strong>${data.certification_number}</strong></p>
                        <a href="/kebs/labels/${data.label_id}/download/" class="btn btn-primary mt-2" target="_blank">
                            <i class="bi bi-download"></i> Download Label
                        </a>
                    </div>
                `;
                resolve({ success: true, message: messageHTML });
            } else {
                reject(new Error(data.message || 'Unknown error generating label'));
            }
        })
        .catch(error => {
            console.error('Label generation error:', error);
            let errorMessage = error.message || 'Error generating label. Please try again.';
            reject(new Error(errorMessage));
        });
    });
}

/**
 * Get the value of a cookie by name
 * @param {string} name - Cookie name
 * @returns {string|null} - Cookie value or null if not found
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
 * Display a message in a container
 * @param {string} containerId - ID of the container element
 * @param {string} message - HTML message to display
 * @param {string} type - Message type (success, error, info)
 */
function displayMessage(containerId, message, type = 'info') {
    const container = document.getElementById(containerId);
    if (!container) return;

    let alertClass = 'alert-info';
    if (type === 'success') alertClass = 'alert-success';
    if (type === 'error') alertClass = 'alert-danger';

    container.innerHTML = `<div class="alert ${alertClass}">${message}</div>`;
}