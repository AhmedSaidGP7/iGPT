document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('reservation-form');
    const reservationUrl = form.dataset.url;  // نأخد URL من data attribute

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        const selectedRooms = [...document.querySelectorAll('.available-room-btn.btn-success')].map(btn => btn.dataset.roomId);
        formData.append('selected_rooms', JSON.stringify(selectedRooms));

        fetch(reservationUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log(data);
            if (data.status === 'success') {
                const modal = document.getElementById('confirmationModal');
                const modalBody = modal.querySelector('.modal-body');
                modalBody.innerHTML = data.html;
                const bootstrapModal = new bootstrap.Modal(modal);
                bootstrapModal.show();
            } else {
                alert(data.message || 'حدث خطأ!');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('حدث خطأ أثناء الاتصال بالخادم.');
        });
    });
});
