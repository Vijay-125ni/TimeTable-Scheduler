/**
 * Utility to prevent duplicate API calls and submissions
 * Ensures a function can only be called once within a specified timeframe
 */

const apiCallTimestamps = {};

/**
 * Prevents duplicate API calls to the same endpoint
 * @param {string} key - Unique identifier for the API call (e.g., 'createDepartment')
 * @param {number} delayMs - Minimum delay between calls (default: 1000ms)
 * @returns {boolean} - true if call is allowed, false if blocked
 */
export function canMakeAPICall(key, delayMs = 1000) {
  const now = Date.now();
  const lastCallTime = apiCallTimestamps[key] || 0;
  
  if (now - lastCallTime >= delayMs) {
    apiCallTimestamps[key] = now;
    return true;
  }
  
  return false;
}

/**
 * Reset API call timestamp
 * @param {string} key - Unique identifier to reset
 */
export function resetAPICallTimer(key) {
  delete apiCallTimestamps[key];
}

/**
 * Debounce function - delays function execution
 * @param {function} func - Function to debounce
 * @param {number} delayMs - Delay in milliseconds
 * @returns {function} - Debounced function
 */
export function debounce(func, delayMs = 300) {
  let timeoutId;
  
  return function debounced(...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func(...args), delayMs);
  };
}

/**
 * Throttle function - limits function execution frequency
 * @param {function} func - Function to throttle
 * @param {number} limitMs - Limit in milliseconds
 * @returns {function} - Throttled function
 */
export function throttle(func, limitMs = 300) {
  let inThrottle;
  
  return function throttled(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limitMs);
    }
  };
}
