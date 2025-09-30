document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".toggle-availability").forEach(button => {
        button.addEventListener("click", function () {
            let soldierId = this.getAttribute("data-id");
            let csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;

            fetch(toggleAvailabilityURL, {  
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": csrfToken
                },
                body: "soldier_id=" + soldierId
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    let statusCell = this.closest("td");
                    let newState = data.is_available;


                    
                    // Update text and button appearance
    
                    statusCell.innerHTML = `
                      
                        <button class="toggle-availability btn ${newState ? "btn-danger" : "btn-primary"}" data-id="${soldierId}">
                            ${newState ? "إلغاء الإتاحة" : "إتاحة"}
                        </button>
                    `;

                    // Reattach event listener
                    statusCell.querySelector(".toggle-availability").addEventListener("click", arguments.callee);
                }
            })
            .catch(error => console.error("Error:", error));
        });
    });
});
