import { Radar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

export default function CoverageRadarChart({ testsByType }) {
  // Derive radar metrics: for each test type, show coverage breadth
  // If tests_by_type has api/ui/perf, show their counts on the radar
  const types = ['api', 'ui', 'perf'];
  const labels = types.map((t) => ({ api: 'API', ui: 'UI', perf: 'Perf' })[t]);
  const values = types.map((t) => testsByType?.[t] || 0);

  const data = {
    labels,
    datasets: [
      {
        label: '测试类型覆盖',
        data: values,
        backgroundColor: 'rgba(88, 166, 255, 0.15)',
        borderColor: '#58a6ff',
        borderWidth: 2,
        pointBackgroundColor: '#58a6ff',
        pointBorderColor: '#0d1117',
        pointBorderWidth: 1,
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    scales: {
      r: {
        beginAtZero: true,
        grid: { color: '#21262d' },
        angleLines: { color: '#21262d' },
        pointLabels: { color: '#8b949e', font: { size: 11 } },
        ticks: {
          color: '#484f58',
          backdropColor: 'transparent',
          font: { size: 10 },
          stepSize: 1,
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1c2128',
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        borderColor: '#30363d',
        borderWidth: 1,
        padding: 8,
        bodyFont: { size: 12 },
      },
    },
  };

  return (
    <div className="chart-container">
      <h3 className="text-sm font-medium text-gray-400 mb-3">参数覆盖</h3>
      <Radar data={data} options={options} />
    </div>
  );
}
