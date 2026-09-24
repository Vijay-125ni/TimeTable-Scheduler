import { useEffect, useRef } from 'react';

/**
 * Custom hook for caching form values to localStorage
 * Saves form data when it changes and restores it on component mount
 * Debounced to optimize performance
 * 
 * @param {string} cacheKey - Unique key for localStorage (e.g., 'departmentFormCache')
 * @param {object} formValues - The current form values from react-hook-form watch()
 * @param {function} setValue - The setValue function from react-hook-form
 * @param {boolean} isFormVisible - Whether the form is currently visible/active
 * @param {boolean} isEditing - Whether we're editing (don't cache when editing)
 * @param {number} debounceMs - Debounce delay in milliseconds (default: 500)
 * @returns {object} - { cachedData, clearCache }
 */
export function useFormCache(cacheKey, formValues, setValue, isFormVisible = true, isEditing = false, debounceMs = 500) {
  const debounceTimer = useRef(null);

  // Restore cached values on mount
  useEffect(() => {
    if (isFormVisible && !isEditing) {
      const cachedData = localStorage.getItem(cacheKey);
      if (cachedData) {
        try {
          const parsed = JSON.parse(cachedData);
          Object.keys(parsed).forEach(key => {
            if (parsed[key] !== '' && parsed[key] !== null && parsed[key] !== undefined) {
              setValue(key, parsed[key]);
            }
          });
        } catch (error) {
          console.warn(`Failed to restore cache for ${cacheKey}:`, error);
        }
      }
    }
  }, [cacheKey, isFormVisible, isEditing, setValue]);

  // Save form values with debouncing (only when form is visible and not editing)
  useEffect(() => {
    if (!isFormVisible || isEditing || Object.keys(formValues).length === 0) {
      return;
    }

    // Clear previous timer
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    // Set new timer - save after debounce delay
    debounceTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(cacheKey, JSON.stringify(formValues));
      } catch (error) {
        console.warn(`Failed to save cache for ${cacheKey}:`, error);
      }
    }, debounceMs);

    // Cleanup timer on unmount
    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [formValues, isFormVisible, isEditing, cacheKey, debounceMs]);

  // Function to clear the cache
  const clearCache = () => {
    try {
      localStorage.removeItem(cacheKey);
    } catch (error) {
      console.warn(`Failed to clear cache for ${cacheKey}:`, error);
    }
  };

  // Get cached data
  const getCachedData = () => {
    try {
      const cached = localStorage.getItem(cacheKey);
      return cached ? JSON.parse(cached) : null;
    } catch (error) {
      console.warn(`Failed to get cached data for ${cacheKey}:`, error);
      return null;
    }
  };

  return { 
    cachedData: getCachedData(), 
    clearCache 
  };
}
