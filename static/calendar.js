document.addEventListener('DOMContentLoaded', () => {
    const monthYearEl = document.getElementById('month-year');
    const calendarDaysEl = document.getElementById('calendar-days');
    const prevMonthBtn = document.getElementById('prev-month');
    const nextMonthBtn = document.getElementById('next-month');

    let currentDate = new Date();
    let archiveDates = [];

    async function fetchArchiveDates() {
        try {
            const response = await fetch('/api/archive-dates');
            if (!response.ok) throw new Error('Failed to fetch archive dates');
            archiveDates = await response.json();
        } catch (error) {
            console.error(error);
            calendarDaysEl.innerHTML = '<div class="text-center text-danger p-4">Could not load archive data.</div>';
        }
    }

    function renderCalendar() {
        calendarDaysEl.innerHTML = '<div class="text-center p-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';
        
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();

        monthYearEl.textContent = `${currentDate.toLocaleString('default', { month: 'long' })} ${year}`;

        const firstDayOfMonth = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();

        // Clear previous content
        calendarDaysEl.innerHTML = '';

        // Add empty cells for days before the first of the month
        for (let i = 0; i < firstDayOfMonth; i++) {
            const dayCell = document.createElement('div');
            dayCell.classList.add('calendar-day', 'not-in-month');
            calendarDaysEl.appendChild(dayCell);
        }

        // Add cells for each day of the month
        for (let i = 1; i <= daysInMonth; i++) {
            const dayCell = document.createElement('div');
            dayCell.classList.add('calendar-day');
            
            const dayNumber = document.createElement('div');
            dayNumber.classList.add('day-number');
            dayNumber.textContent = i;
            dayCell.appendChild(dayNumber);

            const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
            if (archiveDates.includes(dateStr)) {
                dayCell.classList.add('has-data');
                dayCell.title = `View archived data for ${dateStr}`;
                dayCell.addEventListener('click', () => {
                    window.location.href = `/?date=${dateStr}`;
                });
            }
            
            calendarDaysEl.appendChild(dayCell);
        }
    }

    prevMonthBtn.addEventListener('click', () => {
        currentDate.setMonth(currentDate.getMonth() - 1);
        renderCalendar();
    });

    nextMonthBtn.addEventListener('click', () => {
        currentDate.setMonth(currentDate.getMonth() + 1);
        renderCalendar();
    });

    async function init() {
        await fetchArchiveDates();
        renderCalendar();
    }

    init();
});
