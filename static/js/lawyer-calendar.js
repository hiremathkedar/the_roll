(() => {
    const slotElements = [...document.querySelectorAll('[data-calendar-date]')];
    const availableDates = new Set(slotElements.map(slot => slot.dataset.calendarDate));
    const monthLabel = document.getElementById('calendar-month');
    const daysGrid = document.getElementById('calendar-days');
    const selectedLabel = document.getElementById('selected-date-label');
    if (!monthLabel || !daysGrid || !selectedLabel) return;
    daysGrid.style.display = 'grid';
    daysGrid.style.gridTemplateColumns = 'repeat(7, minmax(0, 1fr))';
    daysGrid.style.gap = '5px';

    const today = new Date();
    let shownMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    const dateKey = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

    function renderCalendar() {
        monthLabel.textContent = shownMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
        daysGrid.replaceChildren();
        const offset = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1).getDay();
        const dayCount = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + 1, 0).getDate();
        const rowCount = Math.ceil((offset + dayCount) / 7);
        for (let cell = 0; cell < rowCount * 7; cell++) {
            const day = cell - offset + 1;
            if (day < 1 || day > dayCount) {
                daysGrid.append(document.createElement('span'));
                continue;
            }
            const date = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), day);
            const key = dateKey(date);
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'calendar-day';
            button.textContent = day;
            button.disabled = !availableDates.has(key) || date < new Date(today.getFullYear(), today.getMonth(), today.getDate());
            if (availableDates.has(key)) button.classList.add('has-times');
            button.addEventListener('click', () => {
                daysGrid.querySelectorAll('.selected').forEach(item => item.classList.remove('selected'));
                button.classList.add('selected');
                selectedLabel.textContent = date.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
                slotElements.forEach(slot => { slot.hidden = slot.dataset.calendarDate !== key; });
            });
            daysGrid.append(button);
        }
    }

    document.getElementById('calendar-prev').addEventListener('click', () => {
        shownMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() - 1, 1);
        renderCalendar();
    });
    document.getElementById('calendar-next').addEventListener('click', () => {
        shownMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + 1, 1);
        renderCalendar();
    });

    const confirmation = document.getElementById('booking-confirm-modal');
    if (confirmation) {
        let pendingForm = null;
        let returnFocus = null;
        const closeConfirmation = () => {
            confirmation.hidden = true;
            pendingForm = null;
            if (returnFocus) returnFocus.focus();
        };
        document.querySelectorAll('.booking-slot-form').forEach(form => {
            form.addEventListener('submit', event => {
                event.preventDefault();
                pendingForm = form;
                returnFocus = document.activeElement;
                confirmation.hidden = false;
                document.getElementById('booking-confirm-ok').focus();
            });
        });
        document.getElementById('booking-confirm-ok').addEventListener('click', () => {
            if (pendingForm) pendingForm.submit();
        });
        document.getElementById('booking-confirm-cancel').addEventListener('click', closeConfirmation);
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !confirmation.hidden) closeConfirmation();
        });
    }
    renderCalendar();
})();
