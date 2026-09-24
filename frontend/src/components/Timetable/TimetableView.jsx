import React, { useState, useEffect } from 'react';
import { timetableAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import ConfirmationModal from '../Layout/ConfirmationModal';
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

const addCanvasToSinglePdfPage = (pdf, canvas, { pageWidth, pageHeight, margin }, hasRenderedPage) => {
  const availableWidth = pageWidth - (margin * 2);
  const availableHeight = pageHeight - (margin * 2);
  const pdfScale = Math.min(availableWidth / canvas.width, availableHeight / canvas.height);
  const imgWidth = canvas.width * pdfScale;
  const imgHeight = canvas.height * pdfScale;
  const x = margin + ((availableWidth - imgWidth) / 2);
  const y = margin + ((availableHeight - imgHeight) / 2);

  if (hasRenderedPage) pdf.addPage();

  const imgData = canvas.toDataURL('image/jpeg', 0.98);
  pdf.addImage(imgData, 'JPEG', x, y, imgWidth, imgHeight);

  return true;
};

export default function TimetableView() {
  const [timetables, setTimetables] = useState([]);
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState('classes');
  const [activeSheetKey, setActiveSheetKey] = useState(null);
  const { showToast } = useToast();

  // Modal State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [timetableToDelete, setTimetableToDelete] = useState(null);

  useEffect(() => { loadTimetables(); }, []);

  useEffect(() => {
    if (!selected || !selected.schedule_data) return;
    let keys = [];
    if (activeTab === 'classes') {
      keys = Object.values(selected.schedule_data).map(c => c.class_name);
    } else if (activeTab === 'faculty') {
      keys = Object.keys(getFacultySchedule(selected.schedule_data) || {}).sort();
    } else if (activeTab === 'rooms') {
      keys = Object.keys(getRoomSchedule(selected.schedule_data) || {}).sort();
    }
    if (keys.length > 0 && (!activeSheetKey || !keys.includes(activeSheetKey))) {
      setActiveSheetKey(keys[0]);
    }
  }, [activeTab, selected, activeSheetKey]);

  const loadTimetables = async () => {
    try {
      const res = await timetableAPI.getAll();
      setTimetables(res.data);
    } catch (error) {
      console.error("Failed to load timetables");
      showToast("Failed to load timetables", "error");
    }
  };

  const viewTimetable = async (id) => {
    try {
      const res = await timetableAPI.getById(id);
      setSelected(res.data);
    } catch (error) {
      console.error("Failed to load details");
      showToast("Failed to load details", "error");
    }
  };

  const handleDelete = (e, id) => {
    e.stopPropagation();
    setTimetableToDelete(id);
    setIsDeleteModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!timetableToDelete) return;
    try {
      await timetableAPI.delete(timetableToDelete);
      setTimetables(timetables.filter(t => t.id !== timetableToDelete));
      if (selected?.id === timetableToDelete) setSelected(null);
      showToast("Timetable deleted!", "success");
    } catch (error) {
      showToast("Failed to delete timetable", "error");
    }
  };

  // --- DOWNLOAD HANDLER ---
  const handleDownload = async () => {
    console.log("handleDownload started!");
    console.log("Selected timetable data:", selected);
    if (!selected) {
      console.log("selected is null or undefined!");
      return;
    }

    showToast("Generating PDF... Please wait.", "info");

    const pdf = new jsPDF('landscape', 'pt', 'a4');
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 20;

    // Create a hidden container in the DOM
    const wrapper = document.createElement('div');
    wrapper.style.position = 'absolute';
    wrapper.style.left = '-9999px';
    wrapper.style.top = '0';
    wrapper.style.width = '1200px';
    wrapper.style.display = 'inline-block';
    wrapper.style.padding = '20px';
    wrapper.style.boxSizing = 'border-box';
    wrapper.style.overflow = 'visible';
    wrapper.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    wrapper.style.color = '#111827';
    wrapper.style.background = '#ffffff';
    document.body.appendChild(wrapper);

    try {
      const pagesHTML = [];

      // 1. Build Class Pages
      if (selected.schedule_data) {
        Object.values(selected.schedule_data).forEach(cs => {
          const firstDay = Object.keys(cs.timetable)[0];
          const headers = cs.timetable[firstDay].map(slot => {
            const isBreak = slot.slot_type === 'break';
            const label = isBreak ? (slot.label || 'Break') : `Period ${slot.period}`;
            return `<th style="padding:8px 12px;background:${isBreak ? '#fff7ed' : '#f3f4f6'};border:1px solid #d1d5db;min-width:${isBreak ? '110px' : '130px'};text-align:center;font-size:11px;">
              <div style="font-weight:700;text-transform:uppercase;color:${isBreak ? '#9a3412' : '#374151'};">${label}</div>
              <div style="color:#9ca3af;font-family:monospace;font-size:10px;margin-top:2px;">${slot.time}</div>
            </th>`;
          }).join('');

          const rows = Object.entries(cs.timetable).map(([day, periods]) => {
            const cells = periods.map(slot => {
              if (slot.slot_type === 'break') {
                return `<td style="padding:8px;border:1px solid #d1d5db;text-align:center;background:#fffbeb;color:#92400e;font-size:12px;font-weight:700;text-transform:uppercase;">${slot.label || 'Break'}</td>`;
              }
              if (!slot.subject) return `<td style="padding:8px;border:1px solid #d1d5db;text-align:center;color:#d1d5db;font-size:11px;font-style:italic;">Free</td>`;
              const bg = slot.is_lab ? '#eff6ff' : '#f0fdf4';
              const border = slot.is_lab ? '#bfdbfe' : '#bbf7d0';
              const color = slot.is_lab ? '#1e3a8a' : '#14532d';
              const customMarker = slot.is_custom ? '<span style="float:right;font-size:11px;" title="User Constraint">📌</span>' : '';
              return `<td style="padding:6px;border:1px solid #d1d5db;vertical-align:top;">
                <div style="background:${bg};border:1px solid ${border};color:${color};border-radius:6px;padding:6px;height:100%;min-height:80px;">
                  <div style="font-weight:700;font-size:12px;word-break:break-word;">${customMarker}${slot.subject}</div>
                  <div style="font-size:10px;opacity:0.7;margin-top:2px;word-break:break-word;">${slot.subject_code || ''}</div>
                  <div style="font-size:11px;margin-top:6px;padding-top:4px;border-top:1px solid rgba(0,0,0,0.08);word-break:break-word;"><span style="opacity:0.8;">Faculty:</span> ${slot.faculty}</div>
                  ${slot.room ? `<div style="font-size:10px;margin-top:3px;opacity:0.8;word-break:break-word;"><span>Room:</span> ${slot.room}${slot.room_changed ? ' *' : ''}</div>` : ''}
                </div>
              </td>`;
            }).join('');
            return `<tr>
              <td style="padding:10px 14px;border:1px solid #d1d5db;font-weight:600;color:#374151;background:#f9fafb;white-space:nowrap;">${day}</td>
              ${cells}
            </tr>`;
          }).join('');

          pagesHTML.push(`
            <div>
              <div style="margin-bottom:20px;">
                <h1 style="font-size:22px;font-weight:800;margin-bottom:4px;color:#111827;">${selected.name} <span style="font-size:14px;font-weight:400;color:#6b7280;margin-left:12px;">(Class View)</span></h1>
                <h3 style="font-size:17px;font-weight:700;color:#111827;margin-bottom:4px;">${cs.class_name}</h3>
                <p style="font-size:13px;color:#6b7280;">${cs.department} • ${cs.batch_name}</p>
              </div>
              <table style="border-collapse:collapse;width:100%;">
                <thead><tr>
                  <th style="padding:8px 14px;background:#f3f4f6;border:1px solid #d1d5db;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#6b7280;">Day</th>
                  ${headers}
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          `);
        });
      }

      // 2. Build Faculty Pages
      const facData = getFacultySchedule(selected.schedule_data);
      if (facData && selected.schedule_data) {
        const firstClassKey = Object.keys(selected.schedule_data)[0];
        if (firstClassKey) {
          const masterTimetable = selected.schedule_data[firstClassKey].timetable;
          const days = Object.keys(masterTimetable);
          const masterSlotsTemplate = masterTimetable[days[0]];

          const headers = masterSlotsTemplate.map(slot => {
            const isBreak = slot.slot_type === 'break';
            const label = isBreak ? (slot.label || 'Break') : `Period ${slot.period}`;
            return `<th style="padding:8px 12px;background:${isBreak ? '#fff7ed' : '#f3f4f6'};border:1px solid #d1d5db;min-width:${isBreak ? '110px' : '130px'};text-align:center;font-size:11px;">
              <div style="font-weight:700;text-transform:uppercase;color:${isBreak ? '#9a3412' : '#374151'};">${label}</div>
              <div style="color:#9ca3af;font-family:monospace;font-size:10px;margin-top:2px;">${slot.time}</div>
            </th>`;
          }).join('');

          Object.entries(facData).sort().forEach(([facultyName, schedule]) => {
            const rows = days.map(day => {
              const facultyDaySlots = schedule[day] || [];
              const cells = masterSlotsTemplate.map(slot => {
                if (slot.slot_type === 'break') {
                  return `<td style="padding:8px;border:1px solid #d1d5db;text-align:center;background:#fffbeb;color:#92400e;font-size:12px;font-weight:700;text-transform:uppercase;">${slot.label || 'Break'}</td>`;
                }
                const assignedSlot = facultyDaySlots.find(s => s.period === slot.period);
                if (!assignedSlot) {
                  return `<td style="padding:8px;border:1px solid #d1d5db;text-align:center;color:#d1d5db;font-size:11px;font-style:italic;">Free</td>`;
                }
                return `<td style="padding:6px;border:1px solid #d1d5db;vertical-align:top;">
                  <div style="background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;border-radius:6px;padding:6px;height:100%;min-height:80px;">
                    <div style="font-weight:700;font-size:12px;word-break:break-word;">${assignedSlot.class_name}</div>
                    <div style="font-size:11px;margin-top:6px;padding-top:4px;border-top:1px solid rgba(0,0,0,0.08);word-break:break-word;"><span style="opacity:0.8;">Subject:</span> ${assignedSlot.subject}</div>
                    <div style="font-size:10px;opacity:0.7;margin-top:2px;word-break:break-word;">${assignedSlot.subject_code || ''}</div>
                    ${assignedSlot.room ? `<div style="font-size:10px;opacity:0.75;margin-top:3px;word-break:break-word;">Room: ${assignedSlot.room}${assignedSlot.room_changed ? ' *' : ''}</div>` : ''}
                  </div>
                </td>`;
              }).join('');

              return `<tr>
                <td style="padding:10px 14px;border:1px solid #d1d5db;font-weight:600;color:#374151;background:#f9fafb;white-space:nowrap;">${day}</td>
                ${cells}
              </tr>`;
            }).join('');

            pagesHTML.push(`
              <div>
                <div style="margin-bottom:20px;">
                  <h1 style="font-size:22px;font-weight:800;margin-bottom:4px;color:#111827;">${selected.name} <span style="font-size:14px;font-weight:400;color:#6b7280;margin-left:12px;">(Faculty View)</span></h1>
                  <h3 style="font-size:18px;font-weight:700;color:#111827;margin-bottom:4px;">${facultyName}</h3>
                </div>
                <table style="border-collapse:collapse;width:100%;">
                  <thead><tr>
                    <th style="padding:8px 14px;background:#f3f4f6;border:1px solid #d1d5db;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#6b7280;">Day</th>
                    ${headers}
                  </tr></thead>
                  <tbody>${rows}</tbody>
                </table>
              </div>
            `);
          });
        }
      }

      // 3. Render each page sequentially
      console.log("Total pages to render:", pagesHTML.length);
      let hasRenderedPage = false;
      for (let i = 0; i < pagesHTML.length; i++) {
        console.log(`Rendering page ${i + 1}/${pagesHTML.length}...`);
        wrapper.innerHTML = pagesHTML[i];

        const contentWidth = Math.ceil(wrapper.scrollWidth);
        const contentHeight = Math.ceil(wrapper.scrollHeight);
        const canvas = await html2canvas(wrapper, { 
          scale: 2, 
          useCORS: true,
          logging: false,
          backgroundColor: '#ffffff',
          windowWidth: contentWidth,
          windowHeight: contentHeight,
          width: contentWidth,
          height: contentHeight,
          scrollX: 0,
          scrollY: 0
        });
        console.log(`Finished canvas for page ${i + 1}/${pagesHTML.length}. Converting to image...`);

        hasRenderedPage = addCanvasToSinglePdfPage(
          pdf,
          canvas,
          { pageWidth, pageHeight, margin },
          hasRenderedPage
        );
        console.log(`Page ${i + 1}/${pagesHTML.length} successfully added to PDF.`);
      }
      console.log("Saving PDF...");

      pdf.save(`${selected.name.replace(/[^a-z0-9]/gi, '_')} - Full Schedule.pdf`);
      showToast("PDF downloaded successfully!", "success");

    } catch (err) {
      console.error("PDF generation failed", err);
      showToast("Failed to generate PDF", "error");
    } finally {
      document.body.removeChild(wrapper);
    }
  };

  // --- DATA PIVOTING HELPERS ---

  const getFacultySchedule = (scheduleData) => {
    const facultyMap = {};
    if (!scheduleData) return {};

    Object.values(scheduleData).forEach(classData => {
      Object.entries(classData.timetable).forEach(([day, periods]) => {
        periods.forEach(slot => {
          if (slot.faculty && slot.faculty !== 'TBA') {
            if (!facultyMap[slot.faculty]) facultyMap[slot.faculty] = {};
            if (!facultyMap[slot.faculty][day]) facultyMap[slot.faculty][day] = [];

            facultyMap[slot.faculty][day].push({
              ...slot,
              class_name: classData.class_name
            });
          }
        });
      });
    });
    return facultyMap;
  };

  const getRoomSchedule = (scheduleData) => {
    const roomMap = {};
    if (!scheduleData) return {};

    Object.values(scheduleData).forEach(classData => {
      Object.entries(classData.timetable).forEach(([day, periods]) => {
        periods.forEach(slot => {
          if (slot.room) {
            if (!roomMap[slot.room]) roomMap[slot.room] = {};
            if (!roomMap[slot.room][day]) roomMap[slot.room][day] = [];

            roomMap[slot.room][day].push({
              ...slot,
              class_name: classData.class_name
            });
          }
        });
      });
    });
    return roomMap;
  };


  // --- RENDERERS ---

  const getSlotLabel = (slot) => (
    slot.slot_type === 'break' ? (slot.label || 'Break') : `Period ${slot.period}`
  );

  const renderClassView = () => {
    const classSchedule = selected.schedule_data && Object.values(selected.schedule_data).find(c => c.class_name === activeSheetKey);
    if (!classSchedule) return null;

    const subjectMapping = {};
    Object.values(classSchedule.timetable).forEach(periods => {
      periods.forEach(slot => {
        if (slot.subject && slot.subject_code) {
          if (!subjectMapping[slot.subject_code]) {
            subjectMapping[slot.subject_code] = {
              code: slot.subject_code,
              name: slot.subject,
              type: slot.is_lab ? 'LAB' : 'Theory',
              faculty: slot.faculty,
              credits: slot.credits || '-',
              L: '-',
              T: '-',
              P: '-'
            };
          } else if (slot.is_lab && subjectMapping[slot.subject_code].type === 'Theory') {
            subjectMapping[slot.subject_code].type = 'Blended';
          }
        }
      });
    });
    const mappedSubjects = Object.values(subjectMapping);

    return (
      <div className="h-full flex flex-col bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="border-b border-gray-100 p-4 shrink-0 bg-white">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-2">
            <div>
              <h3 className="text-xl font-bold text-gray-800">{classSchedule.class_name}</h3>
              <p className="text-sm text-gray-500">{classSchedule.department} • {classSchedule.batch_name}{classSchedule.default_room ? ` • ${classSchedule.default_room}` : ''}</p>
            </div>
          </div>
        </div>
        
        {/* Scrollable table container */}
        <div className="visible-scrollbar flex-1 bg-gray-50/50 p-4" style={{ overflowX: 'auto', overflowY: 'auto' }}>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden' }}>
            <table style={{ minWidth: '750px', borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ position: 'sticky', top: 0, left: 0, zIndex: 4, background: '#f9fafb', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', textAlign: 'left', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#6b7280', minWidth: '90px' }}>Day</th>
                  {classSchedule.timetable[Object.keys(classSchedule.timetable)[0]].map((slot, i) => (
                    <th key={i} style={{ position: 'sticky', top: 0, zIndex: 3, background: slot.slot_type === 'break' ? '#fff7ed' : '#f9fafb', padding: '10px 12px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', minWidth: slot.slot_type === 'break' ? '115px' : '145px', textAlign: 'center' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: slot.slot_type === 'break' ? '#9a3412' : '#374151' }}>{getSlotLabel(slot)}</div>
                      <div style={{ fontSize: '10px', color: '#9ca3af', fontFamily: 'monospace', marginTop: '2px' }}>{slot.time}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(classSchedule.timetable).map(([day, periods]) => (
                  <tr key={day}>
                    <td style={{ position: 'sticky', left: 0, zIndex: 1, background: 'rgba(249,250,251,0.97)', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' }}>{day}</td>
                    {periods.map((slot, idx) => (
                      <td key={idx} style={{ padding: '6px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', verticalAlign: 'top', height: '100px' }}>
                        {slot.slot_type === 'break' ? (
                          <div style={{ height: '100%', minHeight: '72px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase' }}>
                            {slot.label || 'Break'}
                          </div>
                        ) : slot.subject ? (
                          <div style={{ height: '100%', padding: '8px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', background: slot.is_lab ? '#eff6ff' : '#f0fdf4', border: `1px solid ${slot.is_lab ? '#bfdbfe' : '#bbf7d0'}`, color: slot.is_lab ? '#1e3a8a' : '#14532d', overflow: 'hidden' }}>
                             <div style={{ fontWeight: 700, fontSize: '13px', lineHeight: 1.3, wordBreak: 'break-word' }}>
                               {slot.subject}{slot.room ? ` (${slot.room})` : ''}
                               {slot.is_custom && (
                                  <span title="User Constraint" style={{ fontSize: '12px', flexShrink: 0, marginLeft: '4px' }}>📌</span>
                               )}
                             </div>
                          </div>
                        ) : (
                          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#d1d5db', fontSize: '11px', fontStyle: 'italic' }}>Free</div>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Mapping Table */}
          {mappedSubjects.length > 0 && (
            <div className="mt-6 border border-gray-200 rounded-lg overflow-hidden bg-white shrink-0">
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
                <thead style={{ background: '#f9fafb' }}>
                  <tr>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>Subject Code</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>Subject Name</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>Type</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>L</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>T</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>P</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>C</th>
                    <th style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', fontWeight: 700, color: '#374151' }}>Faculty Name</th>
                  </tr>
                </thead>
                <tbody>
                  {mappedSubjects.map((sub, idx) => (
                    <tr key={idx} style={{ background: idx % 2 === 0 ? '#ffffff' : '#f9fafb' }}>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.code}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.name}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', color: sub.type === 'LAB' ? '#1e3a8a' : '#14532d', fontWeight: 600 }}>{sub.type}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.L}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.T}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.P}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>{sub.credits}</td>
                      <td style={{ padding: '8px 14px', borderBottom: '1px solid #e5e7eb' }}>{sub.faculty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        </div>
      </div>
    );
  };

  const renderResourceView = (dataMap, type) => {
    const schedule = dataMap[activeSheetKey];
    if (!schedule) return null;

    return (
      <div className="h-full flex flex-col bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="border-b border-gray-100 p-4 shrink-0 bg-white">
          <h3 className="text-xl font-bold text-gray-800">
            {type === 'faculty' ? 'Faculty' : 'Room'}: {activeSheetKey}
          </h3>
        </div>
        
        <div className="visible-scrollbar flex-1 bg-gray-50/50 p-4" style={{ overflowX: 'auto', overflowY: 'auto' }}>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden' }}>
            <table style={{ minWidth: '600px', borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ position: 'sticky', top: 0, left: 0, zIndex: 4, background: '#f9fafb', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', minWidth: '90px', textAlign: 'left' }}>Day</th>
                  <th style={{ position: 'sticky', top: 0, zIndex: 3, background: '#f9fafb', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', textAlign: 'left' }}>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(schedule).map(([day, slots]) => (
                  <tr key={day}>
                    <td style={{ position: 'sticky', left: 0, zIndex: 1, background: 'rgba(249,250,251,0.97)', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', fontWeight: 600, color: '#374151', verticalAlign: 'top', whiteSpace: 'nowrap' }}>{day}</td>
                    <td style={{ padding: '8px', borderBottom: '1px solid #e5e7eb' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {slots.sort((a, b) => a.period - b.period).map((slot, idx) => (
                          <div key={idx} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '6px', padding: '8px', minWidth: '180px' }}>
                            <div style={{ fontSize: '11px', fontFamily: 'monospace', color: '#9ca3af', marginBottom: '4px' }}>
                              {slot.time} (P{slot.period})
                            </div>
                            <div style={{ fontWeight: 700, fontSize: '13px', color: '#2563eb', wordBreak: 'break-word' }}>
                              {slot.class_name}
                            </div>
                            <div style={{ fontSize: '12px', color: '#4b5563', wordBreak: 'break-word' }}>
                              {slot.subject}
                            </div>
                            <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '4px', wordBreak: 'break-word' }}>
                              {type === 'faculty' ? `Room: ${slot.room || '-'}` : `Faculty: ${slot.faculty || '-'}`}
                            </div>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen pb-12">
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Timetable"
        message="Are you sure you want to delete this timetable? This action cannot be undone."
      />

      <h1 className="text-3xl font-bold text-gray-900 mb-8">Timetables Directory</h1>

      {/* List of Timetables */}
      {!selected && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {timetables.map(t => (
            <div
              key={t.id}
              onClick={() => viewTimetable(t.id)}
              className="card hover:shadow-lg transition-all cursor-pointer border-l-4 border-l-primary-500 group relative"
            >
              <button
                onClick={(e) => handleDelete(e, t.id)}
                className="absolute top-4 right-4 text-gray-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
              >
                <span className="text-xl">🗑️</span>
              </button>
              <h3 className="font-bold text-lg mb-1">{t.name}</h3>
              <p className="text-gray-600 mb-4">{t.academic_year} • Semester {t.semester}</p>
              <div className="flex items-center text-sm">
                <span className={`px-2 py-1 rounded-full ${t.solver_status === 'OPTIMAL' ? 'bg-green-100 text-green-700' :
                  t.solver_status === 'FEASIBLE' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
                  }`}>
                  {t.solver_status}
                </span>
              </div>
            </div>
          ))}
          {timetables.length === 0 && (
            <div className="col-span-full text-center py-12 bg-white rounded-lg border border-dashed border-gray-300">
              <p className="text-gray-500 text-lg">No timetables generated yet.</p>
              <p className="text-gray-400 text-sm mt-2">Go to "Generate" page to create one.</p>
            </div>
          )}
        </div>
      )}

      {/* Selected Timetable View */}
      {selected && (
        <div>
          <button
            onClick={() => setSelected(null)}
            className="mb-6 text-gray-500 hover:text-primary-600 flex items-center gap-2 transition-colors"
          >
            ← Back to Directory
          </button>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col" style={{ height: 'calc(100vh - 200px)' }}>
            {/* Header bar */}
            <div className="p-6 border-b border-gray-100 bg-gray-50/50 flex justify-between items-center flex-wrap gap-3 shrink-0">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">{selected.name}</h2>
                <p className="text-gray-500 text-sm mt-1">Status: {selected.solver_status}</p>
              </div>

              {/* TABS + DOWNLOAD */}
              <div className="flex items-center gap-3">
                <div className="flex bg-gray-200/50 p-1 rounded-lg">
                  {['classes', 'faculty', 'rooms'].map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === tab
                        ? 'bg-white text-primary-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                        }`}
                    >
                      {tab.charAt(0).toUpperCase() + tab.slice(1)} View
                    </button>
                  ))}
                </div>

                {/* Download Button */}
                <button
                  onClick={handleDownload}
                  title="Download Timetable as PDF"
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '8px 16px', borderRadius: '8px',
                    background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
                    color: '#fff', fontWeight: 600, fontSize: '14px',
                    border: 'none', cursor: 'pointer', boxShadow: '0 1px 4px rgba(37,99,235,0.3)',
                    transition: 'opacity 0.15s'
                  }}
                  onMouseOver={e => e.currentTarget.style.opacity = '0.88'}
                  onMouseOut={e => e.currentTarget.style.opacity = '1'}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Download PDF
                </button>
              </div>
            </div>

            {/* Scrollable content area */}
            <div className="flex-1 min-h-0 bg-gray-50 p-4">
              {activeTab === 'classes' && renderClassView()}
              {activeTab === 'faculty' && renderResourceView(getFacultySchedule(selected.schedule_data), 'faculty')}
              {activeTab === 'rooms' && renderResourceView(getRoomSchedule(selected.schedule_data), 'rooms')}
            </div>

            {/* Bottom Excel-like Sheet Tabs */}
            <div className="flex items-center bg-gray-100 border-t border-gray-300 overflow-x-auto visible-scrollbar shrink-0" style={{ padding: '0 8px' }}>
              {(() => {
                let keys = [];
                if (activeTab === 'classes' && selected.schedule_data) {
                  keys = Object.values(selected.schedule_data).map(c => c.class_name);
                } else if (activeTab === 'faculty') {
                  keys = Object.keys(getFacultySchedule(selected.schedule_data) || {}).sort();
                } else if (activeTab === 'rooms') {
                  keys = Object.keys(getRoomSchedule(selected.schedule_data) || {}).sort();
                }

                return keys.map(key => (
                  <button
                    key={key}
                    onClick={() => setActiveSheetKey(key)}
                    className={`py-2 px-4 whitespace-nowrap text-sm font-medium border-x border-gray-200 transition-colors ${
                      activeSheetKey === key
                        ? 'bg-white text-primary-700 border-t-[3px] border-t-primary-600 shadow-sm border-b-0 -mb-[1px]'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-50 hover:text-gray-700 border-t-[3px] border-t-transparent'
                    }`}
                    style={{ minWidth: '120px', textAlign: 'center' }}
                  >
                    {key}
                  </button>
                ));
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
