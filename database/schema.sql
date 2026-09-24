-- ================================================
-- AI TIMETABLE SCHEDULER - COMPLETE DATABASE SCHEMA
-- ================================================
-- Database: ai_timetable_scheduler
-- Created: November 2025
-- ================================================

-- Drop database if exists and create fresh
DROP DATABASE IF EXISTS ai_timetable_scheduler;
CREATE DATABASE ai_timetable_scheduler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_timetable_scheduler;

-- ================================================
-- TABLE: users
-- ================================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: departments
-- ================================================
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    head_of_department VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: classes
-- ================================================
CREATE TABLE classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    section VARCHAR(10),
    semester INT,
    student_count INT DEFAULT 0,
    department_id INT NOT NULL,
    academic_year VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    INDEX idx_department (department_id),
    INDEX idx_semester (semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: faculty
-- ================================================
CREATE TABLE faculty (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    department_id INT NOT NULL,
    designation VARCHAR(100),
    max_hours_per_week INT DEFAULT 20,
    min_hours_per_week INT DEFAULT 10,
    unavailable_slots JSON,
    preferences JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    INDEX idx_department (department_id),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: subjects
-- ================================================
CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    hours_per_week INT NOT NULL,
    lecture_duration INT DEFAULT 60,
    requires_lab BOOLEAN DEFAULT FALSE,
    lab_duration INT DEFAULT 120,
    class_id INT NOT NULL,
    faculty_id INT,
    subject_type ENUM('theory', 'practical', 'both') DEFAULT 'theory',
    credits INT DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE SET NULL,
    INDEX idx_class (class_id),
    INDEX idx_faculty (faculty_id),
    INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: time_slots
-- ================================================
CREATE TABLE time_slots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    day_of_week ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_name VARCHAR(50),
    slot_order INT NOT NULL,
    is_break BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_day (day_of_week),
    INDEX idx_order (slot_order),
    UNIQUE KEY unique_day_time (day_of_week, start_time, end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: timetables
-- ================================================
CREATE TABLE timetables (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    academic_year VARCHAR(20) NOT NULL,
    semester INT NOT NULL,
    start_date DATE,
    end_date DATE,
    schedule_data JSON,
    constraints_used JSON,
    solver_status VARCHAR(50),
    solve_time_seconds FLOAT,
    optimization_score FLOAT,
    created_by INT,
    is_active BOOLEAN DEFAULT FALSE,
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_academic_year (academic_year),
    INDEX idx_semester (semester),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: timetable_entries
-- ================================================
CREATE TABLE timetable_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timetable_id INT NOT NULL,
    class_id INT NOT NULL,
    subject_id INT NOT NULL,
    faculty_id INT NOT NULL,
    time_slot_id INT NOT NULL,
    entry_type ENUM('lecture', 'lab', 'tutorial') DEFAULT 'lecture',
    is_locked BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (timetable_id) REFERENCES timetables(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE,
    FOREIGN KEY (time_slot_id) REFERENCES time_slots(id) ON DELETE CASCADE,
    INDEX idx_timetable (timetable_id),
    INDEX idx_class (class_id),
    INDEX idx_faculty (faculty_id),
    INDEX idx_timeslot (time_slot_id),
    UNIQUE KEY unique_slot (timetable_id, time_slot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- TABLE: constraints
-- ================================================
CREATE TABLE constraints (
    id INT AUTO_INCREMENT PRIMARY KEY,
    constraint_type ENUM('hard', 'soft') NOT NULL,
    constraint_name VARCHAR(255) NOT NULL,
    description TEXT,
    constraint_data JSON,
    is_active BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_type (constraint_type),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================
-- INSERT SAMPLE DATA
-- ================================================

-- Admin user (password: admin123)
INSERT INTO users (username, email, hashed_password, full_name, is_active, is_admin) VALUES
('admin', 'admin@timetable.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqP0eUVJYe', 'System Administrator', TRUE, TRUE);

-- Sample departments
INSERT INTO departments (name, code, description) VALUES
('Computer Science', 'CSE', 'Computer Science and Engineering Department'),
('Electronics', 'ECE', 'Electronics and Communication Engineering');

-- Time slots (Monday to Friday, 9 AM - 5 PM)
INSERT INTO time_slots (day_of_week, start_time, end_time, slot_name, slot_order, is_break) VALUES
('Monday', '09:00:00', '10:00:00', 'Period 1', 1, FALSE),
('Monday', '10:00:00', '11:00:00', 'Period 2', 2, FALSE),
('Monday', '11:00:00', '11:15:00', 'Break', 3, TRUE),
('Monday', '11:15:00', '12:15:00', 'Period 3', 4, FALSE),
('Monday', '12:15:00', '13:15:00', 'Period 4', 5, FALSE),
('Monday', '13:15:00', '14:00:00', 'Lunch', 6, TRUE),
('Monday', '14:00:00', '15:00:00', 'Period 5', 7, FALSE),
('Monday', '15:00:00', '16:00:00', 'Period 6', 8, FALSE),
('Monday', '16:00:00', '17:00:00', 'Period 7', 9, FALSE);

-- Repeat for other days (Tuesday-Friday)
INSERT INTO time_slots (day_of_week, start_time, end_time, slot_name, slot_order, is_break)
SELECT 'Tuesday', start_time, end_time, slot_name, slot_order, is_break FROM time_slots WHERE day_of_week = 'Monday';

INSERT INTO time_slots (day_of_week, start_time, end_time, slot_name, slot_order, is_break)
SELECT 'Wednesday', start_time, end_time, slot_name, slot_order, is_break FROM time_slots WHERE day_of_week = 'Monday';

INSERT INTO time_slots (day_of_week, start_time, end_time, slot_name, slot_order, is_break)
SELECT 'Thursday', start_time, end_time, slot_name, slot_order, is_break FROM time_slots WHERE day_of_week = 'Monday';

INSERT INTO time_slots (day_of_week, start_time, end_time, slot_name, slot_order, is_break)
SELECT 'Friday', start_time, end_time, slot_name, slot_order, is_break FROM time_slots WHERE day_of_week = 'Monday';

-- Default constraints
INSERT INTO constraints (constraint_type, constraint_name, description, is_active, priority) VALUES
('hard', 'No Faculty Overlap', 'A faculty member cannot teach in multiple classes at the same time', TRUE, 10),
('hard', 'No Class Overlap', 'A class cannot have multiple subjects at the same time', TRUE, 10),
('hard', 'Faculty Availability', 'Respect faculty unavailable time slots', TRUE, 9),
('soft', 'Balanced Daily Load', 'Distribute subject hours evenly across days', TRUE, 5),
('soft', 'Faculty Preferences', 'Try to honor faculty time preferences', TRUE, 4),
('soft', 'Minimize Gaps', 'Minimize free periods between classes', TRUE, 6),
('soft', 'Lab After Theory', 'Schedule lab sessions after theory classes when possible', TRUE, 3);

SELECT 'Database schema created successfully!' AS Status;
