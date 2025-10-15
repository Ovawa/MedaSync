document.addEventListener('DOMContentLoaded', function() {
    // Form validation for date fields
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => {
        input.addEventListener('change', function() {
            const selectedDate = new Date(this.value);
            const today = new Date();
            
            if (this.name === 'date_of_birth' && selectedDate > today) {
                showAlert('Date of birth cannot be in the future');
                this.value = '';
            }
            
            if (this.name === 'date' && selectedDate < today) {
                showAlert('Cannot select a date in the past');
                this.value = '';
            }
        });
    });
    
    // Phone number input restriction
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        // Restrict to digits only
        input.addEventListener('input', function() {
            this.value = this.value.replace(/[^0-9]/g, '');
        });
        
        // Validate on blur
        input.addEventListener('blur', function() {
            validatePhoneNumber(this.id);
        });
    });
    
    // Time input validation
    const timeInput = document.getElementById('time');
    if (timeInput) {
        timeInput.addEventListener('blur', function() {
            if (this.value && !/^\d{2}:\d{2}$/.test(this.value)) {
                showAlert('Time must be in HH:MM format (e.g., 09:30)');
                this.focus();
            }
        });
    }
    
    // Automatic end time calculation for appointments
    const timeSelect = document.getElementById('time');
    const durationInput = document.getElementById('duration');
    const endTimeInput = document.getElementById('end_time');
    
    function calculateEndTime() {
        if (timeSelect && timeSelect.value && durationInput && durationInput.value) {
            const [hours, minutes] = timeSelect.value.split(':').map(Number);
            const duration = parseInt(durationInput.value);
            
            const totalMinutes = hours * 60 + minutes + duration;
            const endHours = Math.floor(totalMinutes / 60) % 24;
            const endMinutes = totalMinutes % 60;
            
            if (endTimeInput) {
                endTimeInput.value = `${endHours.toString().padStart(2, '0')}:${endMinutes.toString().padStart(2, '0')}`;
            }
        }
    }
    
    if (timeSelect && durationInput) {
        timeSelect.addEventListener('change', calculateEndTime);
        durationInput.addEventListener('input', calculateEndTime);
    }

    // Real-time availability checks for appointments
    const patientSelect = document.getElementById('patient_id');
    const doctorSelect = document.getElementById('doctor_id');
    const dateInput = document.getElementById('date');
    const submitBtn = document.getElementById('submit_btn');
    const availabilityStatus = document.getElementById('availability_status');

    let availabilityTimer = null;
    function debounceCheck() {
        if (availabilityTimer) clearTimeout(availabilityTimer);
        availabilityTimer = setTimeout(checkAvailability, 400);
    }

    function checkAvailability() {
        if (!dateInput || !timeSelect) return;
        const date = dateInput.value;
        const time = timeSelect.value;
        const duration = durationInput ? durationInput.value : '30';
        const patient_id = patientSelect ? patientSelect.value : '';
        const doctor_id = doctorSelect ? doctorSelect.value : '';

        // If no date/time selected, clear status
        if (!date || !time) {
            availabilityStatus.innerHTML = '';
            if (submitBtn) submitBtn.disabled = false;
            return;
        }

        fetch('/check_availability', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date, time, duration, patient_id, doctor_id })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                availabilityStatus.innerHTML = `<small class="form-help text-warning">${data.message || data.error}</small>`;
                if (submitBtn) submitBtn.disabled = false;
                return;
            }

            let messages = [];
            let ok = true;
            if (doctor_id) {
                if (!data.doctor_available) {
                    messages.push('<span class="text-danger">⚠️ Doctor not available at this time</span>');
                    ok = false;
                } else {
                    messages.push('<span class="text-success">✓ Doctor available</span>');
                }
            }

            if (patient_id) {
                if (!data.patient_available) {
                    messages.push('<span class="text-danger">⚠️ Patient already has an appointment at this time</span>');
                    ok = false;
                } else {
                    messages.push('<span class="text-success">✓ Patient available</span>');
                }
            }

            availabilityStatus.innerHTML = messages.join(' &nbsp; | &nbsp; ');
            if (submitBtn) submitBtn.disabled = !ok;

            // Add visual class to availability status
            if (availabilityStatus) {
                availabilityStatus.classList.remove('availability-error', 'availability-ok');
                if (!ok) {
                    availabilityStatus.classList.add('availability-error');
                } else {
                    availabilityStatus.classList.add('availability-ok');
                }
            }
        })
        .catch(err => {
            // On error, do not block submit but show a message
            availabilityStatus.innerHTML = '<small class="form-help text-warning">Could not check availability right now</small>';
            if (submitBtn) submitBtn.disabled = false;
            if (availabilityStatus) {
                availabilityStatus.classList.remove('availability-error', 'availability-ok');
                availabilityStatus.classList.add('availability-error');
            }
        });
    }

    if (dateInput) dateInput.addEventListener('change', debounceCheck);
    if (timeSelect) timeSelect.addEventListener('change', debounceCheck);
    if (durationInput) durationInput.addEventListener('input', debounceCheck);
    if (patientSelect) patientSelect.addEventListener('change', debounceCheck);
    if (doctorSelect) doctorSelect.addEventListener('change', debounceCheck);

    // Run initial check on load if values are present
    if (dateInput && dateInput.value && timeSelect && timeSelect.value) {
        debounceCheck();
    }
    
    // Search functionality
    const searchForms = document.querySelectorAll('.search-bar form');
    searchForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const searchInput = this.querySelector('input[name="search"]');
            if (!searchInput.value.trim()) {
                e.preventDefault();
                window.location.href = window.location.pathname;
            }
        });
    });
});

// Custom alert functions
function showAlert(message) {
    const alert = document.getElementById('custom-alert');
    const overlay = document.getElementById('alert-overlay');
    const messageElement = document.getElementById('alert-message');
    
    if (alert && overlay && messageElement) {
        messageElement.textContent = message;
        alert.style.display = 'block';
        overlay.style.display = 'block';
    }
}

function closeAlert() {
    const alert = document.getElementById('custom-alert');
    const overlay = document.getElementById('alert-overlay');
    
    if (alert && overlay) {
        alert.style.display = 'none';
        overlay.style.display = 'none';
    }
}

// Phone number validation function
function validatePhoneNumber(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return true;
    
    const value = input.value.trim();
    
    // If empty, it's optional
    if (!value) return true;
    
    // Check if it contains only digits and has correct length
    if (!/^\d+$/.test(value)) {
        showAlert('Phone number can only contain digits (0-9)');
        input.focus();
        return false;
    }
    
    if (value.length < 7 || value.length > 15) {
        showAlert('Phone number must be 7-15 digits long (e.g., 812345678)');
        input.focus();
        return false;
    }
    
    return true;
}

// Global function for form validation
window.validatePhoneNumber = function(inputId) {
    return validatePhoneNumber(inputId);
};

// Close alert when clicking outside
document.addEventListener('click', function(event) {
    const alert = document.getElementById('custom-alert');
    const overlay = document.getElementById('alert-overlay');
    
    if (alert && overlay && overlay.style.display === 'block' && event.target === overlay) {
        closeAlert();
    }
});