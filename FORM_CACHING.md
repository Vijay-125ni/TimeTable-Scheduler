# Form Data Caching System

## Overview

This application now includes an automatic form data caching system that saves user input to browser localStorage. When you navigate away from a page and return, your previously entered data is automatically restored.

## Features

✅ **Automatic Saving**: Form data is automatically saved as you type  
✅ **Auto-Restoration**: When you return to a page, cached data is restored  
✅ **Smart Clearing**: Cache is cleared after successful submission  
✅ **Edit Mode Protection**: Cache is not saved when editing existing items  
✅ **Reusable Hook**: Easy to implement across all forms via `useFormCache` hook  

## Implementation

### Custom Hook: `useFormCache`

Location: `/frontend/src/hooks/useFormCache.js`

The `useFormCache` hook handles all caching logic:

```javascript
import { useFormCache } from '../../hooks/useFormCache';

// Inside your component
const formValues = watch();  // From react-hook-form
const { clearCache } = useFormCache(
  'uniqueCacheKey',    // localStorage key
  formValues,          // Form values from watch()
  setValue,            // setValue from useForm()
  showForm,            // Is form visible?
  !!editData           // Are we editing?
);

// After successful submission
clearCache();  // Clears the cache
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cacheKey` | string | Unique localStorage key (e.g., 'departmentFormCache') |
| `formValues` | object | Current form values from `react-hook-form` watch() |
| `setValue` | function | setValue function from useForm() for restoration |
| `isFormVisible` | boolean | Whether the form is currently visible (default: true) |
| `isEditing` | boolean | Whether editing mode is active (default: false) |

## Pages with Caching Implemented

### Managers (Admin Pages)
- ✅ **DepartmentManager** - Caches department form
- ✅ **ClassManager** - Caches class form
- ✅ **BatchManager** - Caches batch configuration form
- ✅ **FacultyManager** - Caches faculty form
- ✅ **SubjectManager** - Caches subject form
- ✅ **FacultyMapping** - Caches dropdown selections (built-in)

### Timetable Pages
- ✅ **TimetableGenerator** - Caches generation parameters

## How It Works

### 1. **Initialization**
When you open a form for the first time:
- The hook checks localStorage for cached data
- If found, the form is auto-populated with previous values
- If not found, the form starts empty

### 2. **During Editing**
As you type:
- Form values are automatically saved to localStorage every time they change
- Changes persist even if you navigate to another page
- The cache only saves when the form is visible and you're NOT editing an existing item

### 3. **On Return**
When you navigate back to a page:
- The hook restores all cached values automatically
- Your previously entered data reappears in the form fields

### 4. **After Submission**
When you successfully create/update an item:
- The cache is automatically cleared via `clearCache()`
- The form resets, ready for new entries
- The page reloads to show the new item

## Cache Keys Used

| Page | Cache Key |
|------|-----------|
| Departments | `departmentFormCache` |
| Classes | `classFormCache` |
| Batches | `batchFormCache` |
| Faculty | `facultyFormCache` |
| Subjects | `subjectFormCache` |
| Timetable Generator | `timetableGeneratorCache` |
| Faculty Mapping | `facultyMappingCache` |

## Example Usage

Here's a simplified example of how to implement caching in a new manager:

```jsx
import { useForm } from 'react-hook-form';
import { useFormCache } from '../../hooks/useFormCache';

export default function MyManager() {
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState(null);
  const { register, handleSubmit, reset, setValue, watch } = useForm();
  const { showToast } = useToast();

  // Get form values
  const formValues = watch();

  // Use cache hook
  const { clearCache } = useFormCache(
    'myFormCache',
    formValues,
    setValue,
    showForm,
    !!editData
  );

  const onSubmit = async (data) => {
    try {
      // Save your data
      await api.create(data);
      showToast('Success!', 'success');
      
      // Clear cache after success
      clearCache();
      reset();
      setEditData(null);
      setShowForm(false);
    } catch (error) {
      showToast('Error!', 'error');
    }
  };

  return (
    <div>
      <button onClick={() => {
        setEditData(null);
        setShowForm(!showForm);
      }}>
        {showForm ? 'Cancel' : 'Add Item'}
      </button>

      {showForm && (
        <form onSubmit={handleSubmit(onSubmit)}>
          <input {...register('name')} />
          <button type="submit">Submit</button>
        </form>
      )}
    </div>
  );
}
```

## Advanced Features

### Manual Cache Restoration (Optional)

The hook provides a `getCachedData()` return value if you need manual control:

```javascript
const { clearCache, cachedData } = useFormCache(...);

// You can manually check what's cached
if (cachedData) {
  console.log('Cached data:', cachedData);
}
```

### Storage Limits

- **Max Size**: Browser localStorage typically allows 5-10 MB per domain
- **Safe Usage**: Form caching uses minimal space (usually < 10 KB per form)
- **Auto-Cleanup**: Cache is cleared after successful submissions

## Browser Compatibility

- ✅ Chrome/Edge 4+
- ✅ Firefox 3.5+
- ✅ Safari 4+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

## Troubleshooting

### Cache Not Showing Up?

1. Check browser console for errors
2. Verify localStorage is enabled in browser settings
3. Clear browser cache and try again
4. Ensure `watch()` is being called from useForm()

### Cache Showing Old Data?

1. Cache is automatically cleared after successful submission
2. Use DevTools → Application → localStorage to manually inspect/delete
3. Manually call `clearCache()` to reset

### Need to Disable Caching?

Simply don't call the `useFormCache` hook in your component. Remove:
```javascript
const { clearCache } = useFormCache(...);
```

## Performance Notes

- Caching operations are minimal and non-blocking
- Data is saved to localStorage asynchronously
- No impact on form performance or rendering
- Suitable for forms with 1-100+ fields

## Adding Caching to New Forms

1. Import the hook:
   ```javascript
   import { useFormCache } from '../../hooks/useFormCache';
   ```

2. Add `watch` to your useForm:
   ```javascript
   const { register, handleSubmit, reset, setValue, watch } = useForm();
   ```

3. Get form values and initialize cache:
   ```javascript
   const formValues = watch();
   const { clearCache } = useFormCache('myUniqueKey', formValues, setValue, showForm, !!editData);
   ```

4. Clear cache after successful submission:
   ```javascript
   clearCache();
   ```

That's it! Your form now has automatic caching.

---

**Created**: May 20, 2026  
**Last Updated**: May 20, 2026
