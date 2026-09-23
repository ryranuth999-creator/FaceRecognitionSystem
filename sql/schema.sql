-- =========================================================
-- Face Recognition Authentication System - SQL Server Schema
-- Run against a fresh database, e.g.:
--   sqlcmd -S localhost -U sa -P "YourStrong@Passw0rd" -d master -Q "CREATE DATABASE FaceRecognitionDB"
--   sqlcmd -S localhost -U sa -P "YourStrong@Passw0rd" -d FaceRecognitionDB -i sql/schema.sql
--
-- Note: app/core/database.py's init_db() will also create these
-- tables automatically via SQLAlchemy on first run. This file is
-- provided for DBAs who prefer to manage schema/migrations by hand.
-- =========================================================

IF OBJECT_ID('dbo.users', 'U') IS NULL
CREATE TABLE dbo.users (
    UserID          INT IDENTITY(1,1) PRIMARY KEY,
    EmployeeID      NVARCHAR(50)  NOT NULL UNIQUE,
    FullName        NVARCHAR(150) NOT NULL,
    Department      NVARCHAR(100) NULL,
    Email           NVARCHAR(150) NULL,
    TelegramID      NVARCHAR(50)  NULL,
    Role            NVARCHAR(20)  NOT NULL DEFAULT 'employee',
    Status          NVARCHAR(20)  NOT NULL DEFAULT 'active',
    HashedPassword  NVARCHAR(255) NULL,
    CreatedDate     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID('dbo.face_embeddings', 'U') IS NULL
CREATE TABLE dbo.face_embeddings (
    EmbeddingID     INT IDENTITY(1,1) PRIMARY KEY,
    UserID          INT NOT NULL REFERENCES dbo.users(UserID) ON DELETE CASCADE,
    EmbeddingVector VARBINARY(MAX) NOT NULL,
    Model           NVARCHAR(50) NOT NULL DEFAULT 'face_recognition_v1_128d',
    CreatedDate     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_face_embeddings_UserID ON dbo.face_embeddings(UserID);

IF OBJECT_ID('dbo.attendance', 'U') IS NULL
CREATE TABLE dbo.attendance (
    AttendanceID    INT IDENTITY(1,1) PRIMARY KEY,
    UserID          INT NOT NULL REFERENCES dbo.users(UserID) ON DELETE CASCADE,
    CheckIn         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CheckOut        DATETIME2 NULL,
    Confidence      FLOAT NOT NULL,
    CameraID        NVARCHAR(50) NULL,
    Photo           NVARCHAR(255) NULL
);
CREATE INDEX IX_attendance_UserID_CheckIn ON dbo.attendance(UserID, CheckIn);

IF OBJECT_ID('dbo.LoginLogs', 'U') IS NULL
CREATE TABLE dbo.LoginLogs (
    LogID           INT IDENTITY(1,1) PRIMARY KEY,
    UserID          INT NOT NULL REFERENCES dbo.users(UserID) ON DELETE CASCADE,
    LoginTime       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    Result          NVARCHAR(20) NOT NULL,   -- success / failed
    Confidence      FLOAT NULL,
    IPAddress       NVARCHAR(50) NULL,
    CameraID        NVARCHAR(50) NULL,
    PhotoPath       NVARCHAR(255) NULL
);
CREATE INDEX IX_LoginLogs_LoginTime ON dbo.LoginLogs(LoginTime);

IF OBJECT_ID('dbo.UnknownFaces', 'U') IS NULL
CREATE TABLE dbo.UnknownFaces (
    UnknownID       INT IDENTITY(1,1) PRIMARY KEY,
    Photo           NVARCHAR(255) NOT NULL,
    Time            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    Confidence      FLOAT NULL,
    CameraID        NVARCHAR(50) NULL,
    Location        NVARCHAR(150) NULL,
    AlertSent       BIT NOT NULL DEFAULT 0,
    EmailSent       BIT NOT NULL DEFAULT 0
);
CREATE INDEX IX_UnknownFaces_Time ON dbo.UnknownFaces(Time);

IF OBJECT_ID('dbo.Cameras', 'U') IS NULL
CREATE TABLE dbo.Cameras (
    CameraID        NVARCHAR(50) PRIMARY KEY,
    CameraName      NVARCHAR(100) NOT NULL,
    IP              NVARCHAR(50) NULL,
    Location        NVARCHAR(150) NULL,
    Status          NVARCHAR(20) NOT NULL DEFAULT 'offline'
);

-- Seed a default camera matching .env.example's DEFAULT_CAMERA_ID
IF NOT EXISTS (SELECT 1 FROM dbo.Cameras WHERE CameraID = 'CAM-01')
INSERT INTO dbo.Cameras (CameraID, CameraName, Location, Status)
VALUES ('CAM-01', 'Main Entrance', 'Front Door', 'offline');
