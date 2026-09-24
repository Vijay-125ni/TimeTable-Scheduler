
# Form Caching - Quick Reference

## What Was Changed?

Form data is now automatically saved to cache files (localStorage) across all pages. When you:
- Type in a form field → **Data is saved automatically**
- Navigate away and come back → **Data is restored**
- Submit the form successfully → **Cache is cleared, form resets**

## Pages with Caching

✅ Department Manager  
✅ Class Manager  
✅ Batch Manager  
✅ Faculty Manager  
✅ Subject Manager  
✅ Faculty Mapping  
✅ Timetable Generator  

## How It Works

### Single Page Workflow

1. **Open Form** → Open a form on any page
2. **Type Data** → Data saves automatically as you type
3. **Navigate Away** → Leave the page, data stays saved in cache
4. **Return to Page** → Your data automatically reappears
5. **Submit** → Cache clears after successful save

### Example: Adding a Department

1. Click "Add Department"
2. Type "Computer Science" in Name field → **Saved**
3. Type "CSE" in Code field → **Saved**
4. Navigate to another page (e.g., Batches)
5. Return to Departments page → **Your data is still there!**
6. Click Submit → Data saved to database, cache cleared

## Developer Implementation

### For New Forms

Three simple steps:

```jsx
// 1. Import the hook
import { useFormCache } from '../../hooks/useFormCache';

// 2. Add this in your component
const formValues = watch();
const { clearCache } = useFormCache('uniqueKey', formValues, setValue, showForm, !!editData);

// 3. Call this after successful submit
clearCache();
```

### Files Modified

**New Files:**
- `/frontend/src/hooks/useFormCache.js` - Main caching hook

**Updated Files:**
- `/frontend/src/components/Admin/DepartmentManager.jsx`
- `/frontend/src/components/Admin/ClassManager.jsx`
- `/frontend/src/components/Admin/BatchManager.jsx`
- `/frontend/src/components/Admin/FacultyManager.jsx`
- `/frontend/src/components/Admin/SubjectManager.jsx`
- `/frontend/src/components/Timetable/TimetableGenerator.jsx`

## Cache Storage

**Location:** Browser's localStorage  
**Size per form:** < 10 KB  
**Total allocated:** 5-10 MB per domain (rarely exceeded)  
**Persistence:** Until manually deleted or cache cleared  

## Clearing Cache

### Automatic (Built-in)
- Cache clears after successful form submission

### Manual Options
1. **DevTools Method:**
   - Right-click → Inspect
   - Go to Application tab
   - Select localStorage
   - Find and delete the cache key

2. **Browser Settings:**
   - Clear browsing data → Cookies and site data

## Testing

Try this:
1. Go to Departments page
2. Click "Add Department"
3. Type "test" in Name field
4. Type "TST" in Code field
5. Go to Batches page (don't submit)
6. Return to Departments page
7. Your data should still be there! ✅

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Data not saving | Check if localStorage is enabled |
| Old data showing | Clear browser cache and retry |
| Cache not clearing | Try refreshing the page after submit |
| Need to reset form | Use browser DevTools to delete cache |

## Technical Details

**Hook Name:** `useFormCache`  
**Hook Path:** `frontend/src/hooks/useFormCache.js`  
**Cache Method:** Browser localStorage API  
**Dependency:** react-hook-form's `watch()` and `setValue()`  

---

For full documentation, see `FORM_CACHING.md`
