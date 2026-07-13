import { Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

export default function CoveragePieChart({ covered, uncovered }) {
  const data = {
    labels: ['已覆盖', '未覆盖'],
    datasets: [
      {
        data: [covered, uncovered],
        backgroundColor: ['#3fb950', '#21262d'],
        borderColor: ['#2ea043', '#30363d'],
        borderWidth: 1,
        hoverBackgroundColor: ['#4ade80', '#343941'],
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    cutout: '65%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#8b949e',
          padding: 16,
          font: { size: 12 },
          usePointStyle: true,
        },
      },
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

  const total = covered + uncovered;
  const pct = total > 0 ? ((covered / total) * 100).toFixed(1) : '0.0';

  return (
    <div className="chart-container">
      <h3 className="text-sm font-medium text-gray-400 mb-3">API 覆盖率</h3>
      <div className="relative flex items-center justify-center">
        <Doughnut data={data} options={options} />
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <span className="text-2xl font-bold text-gray-100">{pct}%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
