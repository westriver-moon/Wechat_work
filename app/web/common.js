(function () {
  function escapeHtml(text) {
    return String(text || '').replace(/[&<>"']/g, function (char) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[char];
    });
  }

  function formatUnixTimestamp(value) {
    const numeric = Number(value || 0);
    if (!numeric) {
      return '-';
    }
    try {
      return new Date(numeric * 1000).toLocaleString('zh-CN');
    } catch (error) {
      return String(value || '');
    }
  }

  window.AppCommon = Object.assign({}, window.AppCommon, {
    escapeHtml,
    formatUnixTimestamp,
  });
})();