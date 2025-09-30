$(document).ready(function () {
    console.log("jQuery Ready!");
    var availableRoomsUrl = $('#get-available-rooms-url').val();
    var today = new Date().toLocaleDateString('en-CA'); // Format: YYYY-MM-DD
    var reservation_id = $('#reservation_id').val();
    console.log("reservation id is ", reservation_id);


    // Set min attributes
    $('#check-in').attr('min', today);
    $('#check-out').attr('min', today);

    // Update check-out date dynamically when check-in changes
    $('#check-in').on('change', function () {
        var checkInDate = $(this).val();
        $('#check-out').val('');
        $('#check-out').attr('min', checkInDate);
    });

    let selectedRooms = [];

    $(document).on('change', '#check-in, #check-out', function () {
        var checkInDate = $('#check-in').val();
        var checkOutDate = $('#check-out').val();

        console.log("Fetching available rooms for:", checkInDate, checkOutDate);

        if (checkInDate && checkOutDate) {
            $.ajax({
                url: availableRoomsUrl,
                method: 'GET',
                data: { check_in: checkInDate, check_out: checkOutDate, reservation_id: reservation_id},
                dataType: 'json',
                success: function (response) {
                    console.log("AJAX Success! Response:", response);
                    $('#available-rooms').empty();
                    selectedRooms = [];
                    updateSelectedRoomsInput();  // Reset hidden input

                    if (response.rooms && Object.keys(response.rooms).length > 0) {
                        $.each(response.rooms, function (unitType, units) {
                            var section = $('<div class="room-section"></div>');
                            section.append('<h4 class="mt-3">' + unitType + '</h4>');

                            var container = $('<div class="available-rooms-container"></div>');
                            units.forEach(function (room) {
                                var button = $('<button type="button" class="btn btn-primary available-room-btn" data-room-id="' + room.id + '">' +
                                    " وحدة رقم " + room.name + " | الدور " + room.floor + " | " + room.view + '</button>');
                                container.append(button);
                            });

                            section.append(container);
                            $('#available-rooms').append(section);
                        });
                    } else {
                        $('#available-rooms').append('<p class="text-danger">لا توجد غرف متاحة.</p>');
                    }
                },
                error: function (xhr, status, error) {
                    console.error("AJAX Error:", status, error);
                    $('#available-rooms').html('<p class="text-danger">حدث خطأ أثناء جلب الغرف المتاحة.</p>');
                }
            });
        }
    });

    // Handle room selection
    $(document).on('click', '.available-room-btn', function () {
        var roomId = $(this).data('room-id');

        if (selectedRooms.includes(roomId)) {
            selectedRooms = selectedRooms.filter(id => id !== roomId);
            $(this).removeClass('btn-success').addClass('btn-primary');
        } else {
            selectedRooms.push(roomId);
            $(this).removeClass('btn-primary').addClass('btn-success');
        }

        console.log("Selected Rooms:", selectedRooms);
        updateSelectedRoomsInput();
    });

    // Update the hidden input with selected rooms
    function updateSelectedRoomsInput() {
        $('#selected-rooms').val(JSON.stringify(selectedRooms));
    }
});
