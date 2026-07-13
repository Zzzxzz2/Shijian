import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const TYPE_LABELS = {
  api: 'API',
  ui: 'UI',
  perf: 'Perf',
};

const TYPE_COLORS = {
  api: { bg: 'rgba(88, 166, 255, 0.7)', border: '#58a6ff' },
  ui: { bg: 'rgba(188, 140, 255, 0.7)', border: '#bc8cff' },
  perf: { bg: 'rgba(210, 153, 34, 0.7)', border: '#d29922' },
};

export default function TestTypeBarChart({ testsByType }) {
  const labels = Object.keys(testsByType || {}).map(
    (k) => TYPE_LABELS[k] || k
  );
  const values = Object.values(testsByType || {});
  const bgColors = Object.keys(testsByType || {}).map(
    (k) => TYPE_COLORS[k]?.bg || 'rgba(139, 148, 158, 0.7)'
  );
  const borderColors = Object.keys(testsByType || {}).map(
    (k) => TYPE_COLORS[k]?.border || '#8b949e'
  );

  const data = {
    labels,
    datasets: [
      {
        label: '用例数',
        data: values,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1,
        borderRadius: 4,
        barThickness: 40,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: true,
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
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#8b949e', font: { size: 11 } },
      },
      y: {
        beginAtZero: true,
        grid: { color: '#21262d', drawBorder: false },
        ticks: {
          color: '#8b949e',
          font: { size: 11 },
          stepSize: 1,
        },
      },
    },
  };

  return (
    <div className="chart-container">
      <h3 className="text-sm font-medium text-gray-400 mb-3">用例分布</h3>
      <Bar data={data} options={options} />
    </div>
  );
}
