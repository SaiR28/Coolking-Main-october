// charts.js

document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.getElementById('temperatureChart');

    if (ctx) {
        // `chartData` is already a JavaScript object from the template
        if (typeof chartData === 'undefined') {
            console.error("Chart data is not defined");
            return;
        }

        const parsedChartData = chartData;

        const datasets = [];
        const colors = [
            'rgba(255, 99, 132, 1)',  // Red
            'rgba(54, 162, 235, 1)',  // Blue
            'rgba(255, 206, 86, 1)',  // Yellow
            'rgba(75, 192, 192, 1)',  // Green
            'rgba(153, 102, 255, 1)', // Purple
            'rgba(255, 159, 64, 1)',  // Orange
            'rgba(199, 199, 199, 1)', // Grey
            'rgba(83, 102, 255, 1)',  // Indigo
            'rgba(255, 99, 255, 1)',  // Pink
            'rgba(99, 255, 99, 1)'    // Light Green
        ];

        let colorIndex = 0;
        
        // Collect all timestamps for x-axis labels.
        // It's important that these are in a format Moment.js can parse,
        // which default SQLite 'YYYY-MM-DD HH:MM:SS' strings are.
        let allTimestamps = new Set(); 

        for (const sensorName in parsedChartData) {
            if (parsedChartData.hasOwnProperty(sensorName)) {
                const data = parsedChartData[sensorName];
                const borderColor = colors[colorIndex % colors.length];
                const backgroundColor = borderColor.replace('1)', '0.2)');

                datasets.push({
                    label: sensorName,
                    // Chart.js expects data points as {x: timestamp, y: value} when using 'time' scale
                    data: data.timestamps.map((ts, index) => ({
                        x: ts, // Raw timestamp string from DB
                        y: data.temperatures[index]
                    })),
                    borderColor: borderColor,
                    backgroundColor: backgroundColor,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 3,
                    pointBackgroundColor: borderColor,
                    pointBorderColor: '#fff',
                    pointHoverRadius: 5
                });

                data.timestamps.forEach(ts => allTimestamps.add(ts));
                colorIndex++;
            }
        }

        new Chart(ctx, {
            type: 'line',
            data: {
                // Labels are not strictly needed with 'time' scale and {x,y} data,
                // but can be used for fallback or explicit control.
                labels: Array.from(allTimestamps).sort(), 
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Temperature Trends Over Time',
                        font: {
                            size: 18,
                            weight: 'bold'
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            // Format the tooltip title (timestamp) to Indian format
                            title: function(context) {
                                if (context && context[0] && context[0].parsed && context[0].parsed.x) {
                                    return moment(context[0].parsed.x).format('DD-MM-YYYY HH:mm:ss');
                                }
                                return '';
                            },
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                label += context.raw.y + ' °C';
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            parser: 'YYYY-MM-DD HH:mm:ss', // Specify the input format of your timestamps
                            tooltipFormat: 'DD-MM-YYYY HH:mm:ss', // Format for tooltip display
                            displayFormats: {
                                minute: 'HH:mm',
                                hour: 'DD MMM HH:mm', // Indian context: Day Month HH:mm
                                day: 'DD MMM',
                                week: 'DD MMM',
                                month: 'MMM YYYY',
                                year: 'YYYY'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Time'
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Temperature (°C)'
                        },
                        beginAtZero: false
                    }
                }
            }
        });
    }
});
