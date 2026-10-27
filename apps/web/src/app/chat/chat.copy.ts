/** Pinned RU chrome — EXPERIENCE State Patterns (network-fail, paste-too-long). */

export const PASTE_TOO_LONG = 'Слишком длинное сообщение. Сократи текст.';
export const NETWORK_FAIL = 'Нет связи. Проверь интернет и попробуй снова.';
/** Singleton /ws conflict — distinct from NETWORK_FAIL (api down / outage). */
export const WS_ALREADY_OPEN =
  'Чат уже открыт в другой вкладке. Закрой его и нажми «Повторить».';
export const UNPARSEABLE_FRAME = 'Не удалось обработать ответ сервера. Попробуй ещё раз.';
export const RETRY_LABEL = 'Повторить';
export const SOON_LABEL = 'Скоро';
export const COMPOSER_PLACEHOLDER = 'Напиши сообщение…';
export const SEND_LABEL = 'Отправить';
export const BRAND_NAME = 'Lingua AI';
export const MAX_MESSAGE_LENGTH = 2000;
