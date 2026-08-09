/**
 * ============================================================
 *  MSI 每日活動報告 — 草稿寄送端
 *
 *  分工：Claude skill 每天抓資料、產 Excel、建立 Gmail 草稿
 *       （主旨固定為「【MSI每日活動報告】YYYY-MM-DD」）
 *       本腳本每天稍晚執行，找到當天的草稿並寄出。
 *
 *  安裝：
 *  1. https://script.google.com → 新專案 → 貼上本檔
 *  2. 執行一次 setup()，授權 Gmail 權限
 *     （會建立每日觸發器；SEND_HOUR 請設在 Claude 排程之後
 *       至少 30 分鐘，例如 Claude 08:00 跑，這裡 09:00 寄）
 *  3. 完成。想停用執行 removeTriggers()
 * ============================================================
 */

const CONFIG = {
  SUBJECT_PREFIX: '【MSI每日活動報告】',  // 必須與 skill 的主旨前綴一致
  SEND_HOUR: 9,                          // 每天幾點寄送（台北時間）
  TZ: 'Asia/Taipei',
  ONLY_TODAY: true,     // true=只寄主旨含今天日期的草稿；false=寄所有前綴相符草稿
  DEDUPE: true,         // 同日多份草稿時只寄最新一份，其餘丟垃圾桶
  NOTIFY_ON_MISS: '',   // 找不到當日草稿時通知的信箱（留空=不通知）
};

function sendDrafts() {
  const today = Utilities.formatDate(new Date(), CONFIG.TZ, 'yyyy-MM-dd');
  const wanted = CONFIG.ONLY_TODAY
      ? CONFIG.SUBJECT_PREFIX + today
      : CONFIG.SUBJECT_PREFIX;

  // 取出主旨相符的草稿，依訊息日期新→舊排序
  const matches = GmailApp.getDrafts()
      .map(d => ({ draft: d, msg: d.getMessage() }))
      .filter(x => (x.msg.getSubject() || '').indexOf(wanted) === 0)
      .sort((a, b) => b.msg.getDate() - a.msg.getDate());

  if (matches.length === 0) {
    Logger.log('今日 (%s) 找不到符合「%s」的草稿', today, wanted);
    if (CONFIG.NOTIFY_ON_MISS) {
      GmailApp.sendEmail(CONFIG.NOTIFY_ON_MISS,
          '⚠ MSI報告草稿缺漏 ' + today,
          '排程時間到了，但 Gmail 草稿匣裡沒有「' + wanted + '」。\n' +
          '請檢查 Claude 排程任務是否執行成功。');
    }
    return;
  }

  // 寄出最新一份
  const sent = matches[0].draft.send();
  Logger.log('已寄出：%s (messageId=%s)',
      sent.getSubject(), sent.getId());

  // 其餘同日重複草稿丟垃圾桶
  if (CONFIG.DEDUPE && matches.length > 1) {
    matches.slice(1).forEach(x => {
      x.msg.moveToTrash();
      Logger.log('重複草稿已移至垃圾桶：%s', x.msg.getSubject());
    });
  }
}

/** 首次安裝執行：授權 + 建立每日觸發器 */
function setup() {
  removeTriggers();
  ScriptApp.newTrigger('sendDrafts')
      .timeBased()
      .everyDays(1)
      .atHour(CONFIG.SEND_HOUR)
      .inTimezone(CONFIG.TZ)
      .create();
  Logger.log('觸發器已建立：每天 %s 點（%s）執行 sendDrafts',
      CONFIG.SEND_HOUR, CONFIG.TZ);
}

/** 停用：移除本專案所有觸發器 */
function removeTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
}
