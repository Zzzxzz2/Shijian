import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

/**
 * Props:
 *   runs — array of { id, status, summary: { pass, fail }, created_at }
 */
export default function ExecutionTrendChart({ runs }) {
  if (!runs || runs.length === 0) {
    return (
      <div className="chart-container">
        <h3 className="text-sm font-medium text-gray-400 mb-3">执行趋势</h3>
        <p className="text-center text-gray-500 py-6 text-sm">暂无执行数据</p>
      </div>
    );
  }

  // Compute pass rate for each run
  const items = runs
    .filter((r) => r.summary)
    .map((r) => {
      const s = typeof r.summary === 'string' ? JSON.parse(r.summary) : r.summary;
      const total = (s.pass || 0) + (s.fail || 0);
      const passRate = total > 0 ? ((s.pass || 0) / total) * 100 : 0;
      return {
        label: r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) : '-',
        passRate: Math.round(passRate * 10) / 10,
        total,
      };
    });

  const data = {
    labels: items.map((i) => i.label),
    datasets: [
      {
        label: '通过率',
        data: items.map((i) => i.passRate),
        fill: true,
        backgroundColor: 'rgba(63, 185, 80, 0.08)',
        borderColor: '#3fb950',
        borderWidth: 2,
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#0d1117',
        pointBorderWidth: 1,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    interaction: {
      intersect: false,
      mode: 'index',
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        backgroundColor: '#1c2128',
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        borderColor: '#30363d',
        borderWidth: 1,
        padding: 10,
        callbacks: {
          label: (ctx) => `通过率: ${ctx.parsed.y}%`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          color: '#8b949e',
          font: { size: 11 },
          maxRotation: 45,
        },
      },
      y: {
        min: 0,
        max: 100,
        grid: { color: '#21262d', drawBorder: false },
        ticks: {
          color: '#8b949e',
          font: { size: 11 },
          callback: (v) => v + '%',
        },
      },
    },
  };

  return (
    <div className="chart-container">
      <h3 className="text-sm font-medium text-gray-400 mb-3">执行趋势</h3>
      <Line data={data} options={options} />
    </div>
  );
}
