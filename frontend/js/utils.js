/* global window.App */
(function () {
  'use strict';

  var utils = {};

  var loadingCount = 0;
  utils.showLoading = function () {
    loadingCount++;
    var el = document.getElementById('loading-overlay');
    if (el) el.classList.remove('hidden');
  };

  utils.hideLoading = function () {
    loadingCount = Math.max(0, loadingCount - 1);
    if (loadingCount) return;
    var el = document.getElementById('loading-overlay');
    if (el) el.classList.add('hidden');
  };

  utils.showToast = function (message, type) {
    type = type || 'success';
    var bgMap = {
      success: 'bg-green-500',
      error: 'bg-red-500',
      warning: 'bg-yellow-500',
      info: 'bg-blue-500',
    };
    var bg = bgMap[type] || bgMap.success;
    var toast = document.createElement('div');
    toast.className = bg + ' text-white px-5 py-3 rounded-lg shadow-lg text-sm z-[60] transition-opacity duration-300';
    toast.textContent = message;

    // Stack toasts vertically
    var container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.setAttribute('role', 'status');
      container.setAttribute('aria-live', 'polite');
      container.className = 'fixed top-4 right-4 z-[60] flex flex-col gap-2';
      document.body.appendChild(container);
    }
    container.appendChild(toast);

    setTimeout(function () {
      toast.style.opacity = '0';
      setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
  };

  utils.escapeHtml = function (str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };

  utils.formatDate = function (dateStr) {
    if (!dateStr) return '-';
    try {
      var d = new Date(/T/.test(dateStr) && !/(Z|[+-]\d{2}:\d{2})$/i.test(dateStr) ? dateStr + 'Z' : dateStr);
      if (isNaN(d.getTime())) return dateStr;
      var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
      return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
        + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    } catch (e) {
      return dateStr;
    }
  };

  window.App = window.App || {};
  window.App.utils = utils;
})();
