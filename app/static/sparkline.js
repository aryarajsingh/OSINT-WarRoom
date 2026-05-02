// Inline SVG sparkline generator — no library needed
document.addEventListener('DOMContentLoaded', function() { renderSparklines(); });
document.addEventListener('htmx:afterSwap', function() { renderSparklines(); });

function renderSparklines() {
    document.querySelectorAll('svg.sparkline').forEach(function(svg) {
        var raw = svg.getAttribute('data-values');
        if (!raw) return;
        var values = raw.split(',').map(Number);
        if (values.length === 0) return;

        var w = parseFloat(svg.getAttribute('width')) || 80;
        var h = parseFloat(svg.getAttribute('height')) || 24;
        var max = Math.max.apply(null, values) || 1;
        var padding = 2;

        var points = values.map(function(v, i) {
            var x = padding + (i / (values.length - 1 || 1)) * (w - padding * 2);
            var y = h - padding - (v / max) * (h - padding * 2);
            return x + ',' + y;
        });

        // Determine color based on trend
        var recent = values.slice(-2);
        var color = '#44aa66'; // green default
        if (recent.length >= 2 && recent[1] > recent[0]) color = '#ff8800'; // orange if rising
        if (recent.length >= 2 && recent[1] > recent[0] * 1.5) color = '#ff3344'; // red if spiking

        svg.innerHTML =
            '<polyline points="' + points.join(' ') +
            '" fill="none" stroke="' + color +
            '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
            '<circle cx="' + points[points.length - 1].split(',')[0] +
            '" cy="' + points[points.length - 1].split(',')[1] +
            '" r="2" fill="' + color + '"/>';
    });
}
