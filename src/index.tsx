import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  staticClasses,
  TextField
} from "@decky/ui";
import {
  definePlugin,
  callable
} from "@decky/api";
import { useEffect, useState, useCallback, FC } from "react";
import { FaDownload, FaPlay, FaStop, FaSync, FaFolder, FaFolderPlus, FaArrowUp, FaCheck } from "react-icons/fa";
import { QRCodeSVG } from "qrcode.react";

const setupTransmission = callable<[], { status: string; message: string }>("setup_transmission");
const stopTransmission = callable<[], { status: string; message: string }>("stop_transmission");
const restartTransmission = callable<[], { status: string; message: string }>("restart_transmission");
const getTransmissionStatus = callable<[], { status: string }>("get_transmission_status");
const getLocalIp = callable<[], string>("get_local_ip");
const getLogs = callable<[], { success: boolean; logs?: { plugin: string; loader: string; container: string }; message?: string }>("get_logs");
const getDownloadPath = callable<[], { download_path: string | null }>("get_download_path");
const setDownloadPath = callable<[path: string], { status: string; message: string }>("set_download_path");
const listDirectories = callable<[path: string], { success: boolean; directories: Array<{name: string, path: string}>, current_path?: string, parent_path?: string, message?: string }>("list_directories");
const createDirectory = callable<[parent_path: string, name: string], { success: boolean, path?: string, message?: string }>("create_directory");
const isDevModeEnabled = callable<[], { enabled: boolean }>("is_dev_mode_enabled");

interface Logs {
  plugin?: string;
  loader?: string;
  container?: string;
}

interface LogsSectionProps {
  showLogs: boolean;
  logs: Logs;
  logsError: string | null;
  onToggleLogs: () => void;
}

const LogsSection: FC<LogsSectionProps> = ({ showLogs, logs, logsError, onToggleLogs }) => {
  return (
    <>
      <ButtonItem layout="below" onClick={onToggleLogs}>
        {showLogs ? "Hide Logs (Dev Only)" : "Show Logs (Dev Only)"}
      </ButtonItem>

      {showLogs && (
        <div style={{ marginTop: "8px", background: "#0d1117", padding: "8px", borderRadius: "4px", border: "1px solid #30363d" }}>
          {logsError ? (
            <p style={{ color: "#ff6b6b", margin: 0, fontSize: "11px" }}>{logsError}</p>
          ) : (
            <div style={{ fontSize: "10px", fontFamily: "monospace", display: "flex", flexDirection: "column", gap: "8px" }}>
              {(["plugin", "loader", "container"] as const).map((key) => {
                const label = key === "plugin" ? "Plugin Logs" : key === "loader" ? "Decky Loader Logs" : "Podman Container Logs";
                return (
                  <div key={key}>
                    <span style={{ color: "#58a6ff", fontWeight: "bold", display: "block", marginBottom: "4px" }}>
                      {label}:
                    </span>
                    <textarea 
                      readOnly 
                      value={logs[key] || "Loading..."} 
                      style={{ 
                        width: "95%", 
                        height: "120px", 
                        background: "#161b22", 
                        color: "#c9d1d9", 
                        border: "1px solid #30363d", 
                        borderRadius: "3px", 
                        fontSize: "9px", 
                        fontFamily: "monospace", 
                        resize: "vertical" 
                      }} 
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </>
  );
};

function Content() {
  const [ipUrl, setIpUrl] = useState<string>("Initializing...");
  const [statusMsg, setStatusMsg] = useState<string>("Checking status...");
  const [containerStatus, setContainerStatus] = useState<string>("unknown");
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [logs, setLogs] = useState<Logs>({});
  const [logsError, setLogsError] = useState<string | null>(null);

  const [downloadPath, setDownloadPathState] = useState<string>("Initializing...");
  const [isConfiguringPath, setIsConfiguringPath] = useState<boolean>(false);
  const [pickerPath, setPickerPath] = useState<string>("root");
  const [pickerDirs, setPickerDirs] = useState<Array<{ name: string; path: string }>>([]);
  const [currentPath, setCurrentPath] = useState<string>("");
  const [parentPath, setParentPath] = useState<string>("");
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState<string>("");
  const [isCreatingFolder, setIsCreatingFolder] = useState<boolean>(false);
  const [isDev, setIsDev] = useState<boolean>(false);

  const isPathInitialized = downloadPath && downloadPath !== "Initializing...";

  const fetchLogs = useCallback(async () => {
    try {
      const res = await getLogs();
      if (res && res.success) {
        setLogs(res.logs || {});
        setLogsError(null);
      } else {
        setLogsError(res?.message || "Failed to fetch logs");
      }
    } catch (e) {
      setLogsError("Error calling get_logs method");
    }
  }, []);

  const handleToggleLogs = useCallback(() => {
    setShowLogs((prev) => {
      const next = !prev;
      if (next) {
        fetchLogs();
      }
      return next;
    });
  }, [fetchLogs]);

  const refreshStatus = useCallback(async () => {
    try {
      const statusRes = await getTransmissionStatus();
      if (statusRes && statusRes.status) {
        setContainerStatus(statusRes.status);
        if (statusRes.status === "running") {
          setStatusMsg("Service is running");
        } else if (statusRes.status === "stopped") {
          setStatusMsg("Service is stopped");
        } else if (statusRes.status === "missing") {
          setStatusMsg("Service is not installed");
        }
      }
    } catch (e) {
      setStatusMsg("Failed to query status");
    }

    try {
      const ip = await getLocalIp();
      if (ip) {
        setIpUrl(ip);
      }
    } catch (e) {
      setIpUrl("http://127.0.0.1:9091");
    }
  }, []);

  const fetchPickerDirs = useCallback(async (path: string) => {
    try {
      const res = await listDirectories(path);
      if (res && res.success) {
        setPickerDirs(res.directories || []);
        setCurrentPath(res.current_path || "");
        setParentPath(res.parent_path || "");
        setPickerError(null);
      } else {
        setPickerError(res?.message || "Failed to load directories.");
      }
    } catch (e) {
      setPickerError("Error loading directories.");
    }
  }, []);

  useEffect(() => {
    if (isConfiguringPath) {
      fetchPickerDirs(pickerPath);
    }
  }, [isConfiguringPath, pickerPath, fetchPickerDirs]);

  const handleCreateFolder = useCallback(async () => {
    if (!newFolderName || !newFolderName.trim()) return;
    try {
      const res = await createDirectory(currentPath, newFolderName);
      if (res && res.success) {
        setIsCreatingFolder(false);
        setNewFolderName("");
        fetchPickerDirs(currentPath);
      } else {
        setPickerError(res?.message || "Failed to create folder.");
      }
    } catch (e) {
      setPickerError("Failed to create folder.");
    }
  }, [currentPath, newFolderName, fetchPickerDirs]);

  useEffect(() => {
    const init = async () => {
      // Check if dev mode is enabled
      try {
        const devRes = await isDevModeEnabled();
        if (devRes && devRes.enabled) {
          setIsDev(true);
        }
      } catch (e) {
        // ignore
      }

      try {
        const pathRes = await getDownloadPath();
        if (pathRes && pathRes.download_path) {
          setDownloadPathState(pathRes.download_path);
          setIsConfiguringPath(false);
          
          // Only start setup if path exists
          const setupRes = await setupTransmission();
          if (setupRes) {
            if (setupRes.status === "failed") {
              setStatusMsg(setupRes.message || "Setup failed");
              setContainerStatus("missing");
              return;
            }
            if (setupRes.message) {
              setStatusMsg(setupRes.message);
            }
          }
        } else {
          setIsConfiguringPath(true);
          setStatusMsg("Configuration required");
        }
      } catch (e) {
        setIsConfiguringPath(true);
        setStatusMsg("Failed to verify settings");
      }
      refreshStatus();
    };
    init();
  }, [refreshStatus]);

  const handleSavePath = useCallback(async (targetPath: string) => {
    if (!targetPath || !targetPath.trim()) {
      setPickerError("Path cannot be empty");
      return;
    }
    setPickerError(null);
    setStatusMsg("Saving folder path...");
    try {
      const res = await setDownloadPath(targetPath);
      if (res && res.status === "success") {
        // Update state and return to main screen immediately — don't wait for server restart
        setDownloadPathState(targetPath);
        setIsConfiguringPath(false);
        setPickerPath("root");
        setStatusMsg("Starting service...");

        // Kick off setup + status refresh in background (fire-and-forget)
        setupTransmission().then((startRes) => {
          if (startRes) {
            if (startRes.status === "failed") {
              setStatusMsg(startRes.message || "Failed to start service");
              setContainerStatus("missing");
              return;
            }
            if (startRes.message) {
              setStatusMsg(startRes.message);
            }
          }
          refreshStatus();
        }).catch(() => {
          setStatusMsg("Failed to start service");
          refreshStatus();
        });
      } else {
        const errMsg = res?.message || "Failed to save path";
        setStatusMsg(errMsg);
        setPickerError(errMsg);
      }
    } catch (e) {
      const errMsg = "Failed to connect to backend";
      setStatusMsg(errMsg);
      setPickerError(errMsg);
    }
  }, [refreshStatus]);

  const handleStart = useCallback(async () => {
    setStatusMsg("Starting service...");
    try {
      const res = await setupTransmission();
      if (res) {
        if (res.status === "failed") {
          setStatusMsg(res.message || "Failed to start service");
          setContainerStatus("missing");
          return;
        }
        if (res.message) {
          setStatusMsg(res.message);
        }
      }
      refreshStatus();
    } catch (e) {
      setStatusMsg("Failed to start service");
    }
  }, [refreshStatus]);

  const handleStop = useCallback(async () => {
    setStatusMsg("Stopping service...");
    try {
      const res = await stopTransmission();
      if (res) {
        if (res.status === "failed") {
          setStatusMsg(res.message || "Failed to stop service");
          return;
        }
        if (res.message) {
          setStatusMsg(res.message);
        }
      }
      refreshStatus();
    } catch (e) {
      setStatusMsg("Failed to stop service");
    }
  }, [refreshStatus]);

  const handleRestart = useCallback(async () => {
    setStatusMsg("Restarting service...");
    try {
      const res = await restartTransmission();
      if (res) {
        if (res.status === "failed") {
          setStatusMsg(res.message || "Failed to restart service");
          setContainerStatus("missing");
          return;
        }
        if (res.message) {
          setStatusMsg(res.message);
        }
      }
      refreshStatus();
    } catch (e) {
      setStatusMsg("Failed to restart service");
    }
  }, [refreshStatus]);

  const getStatusColor = () => {
    if (containerStatus === "running") return "#2ea043"; // Success Green
    if (containerStatus === "stopped") return "#ffc107"; // Warning Yellow
    return "#dc3545"; // Error Red
  };

  if (isConfiguringPath) {
    return (
      <PanelSection title="Folder Browser">
        <PanelSectionRow>
          <div style={{ padding: "4px 0", fontSize: "14px", color: "#dcdcdc" }}>
            <p style={{ margin: "0 0 6px 0", fontSize: "12px", color: "#8a9aab", fontWeight: "bold" }}>
              Current Location:
            </p>
            <div style={{ 
              background: "#11141a", 
              padding: "10px", 
              borderRadius: "4px", 
              border: "1px solid #282e38", 
              marginBottom: "12px", 
              fontFamily: "monospace", 
              fontSize: "12px",
              wordBreak: "break-all"
            }}>
              {pickerPath === "root" ? "Select Storage Drive" : currentPath}
            </div>

            {pickerError && (
              <p style={{ color: "#ff6b6b", margin: "0 0 10px 0", fontSize: "12px" }}>{pickerError}</p>
            )}

            {/* Folder list */}
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto", marginBottom: "12px" }}>
              {/* Go Up button */}
              {pickerPath !== "root" && (
                <ButtonItem
                  layout="below"
                  onClick={() => setPickerPath(parentPath)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <FaArrowUp size={12} color="#ffc107" /> <span>.. (Go Up)</span>
                  </div>
                </ButtonItem>
              )}

              {pickerDirs.map((dir) => (
                <ButtonItem
                  key={dir.path}
                  layout="below"
                  onClick={() => setPickerPath(dir.path)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <FaFolder size={14} color="#3aa3ff" style={{ flexShrink: 0 }} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{dir.name}</span>
                  </div>
                </ButtonItem>
              ))}

              {pickerDirs.length === 0 && !pickerError && pickerPath !== "root" && (
                <p style={{ fontStyle: "italic", color: "#8a9aab", fontSize: "12px", textAlign: "center", margin: "10px 0" }}>
                  This folder is empty.
                </p>
              )}
            </div>

            {/* Actions for current directory selection / creation */}
            {pickerPath !== "root" && (
              <div style={{ borderTop: "1px solid #282e38", paddingTop: "12px", marginTop: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
                {/* New Folder Inline Creator */}
                {!isCreatingFolder ? (
                  <ButtonItem
                    layout="below"
                    onClick={() => setIsCreatingFolder(true)}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}>
                      <FaFolderPlus size={12} /> Create New Folder
                    </div>
                  </ButtonItem>
                ) : (
                  <div style={{ background: "#1a1f24", padding: "8px", borderRadius: "4px", border: "1px solid #3a4450", display: "flex", flexDirection: "column", gap: "8px" }}>
                    <TextField
                      label="Folder Name"
                      value={newFolderName}
                      description="Folder will be created inside current path"
                      onChange={(e) => setNewFolderName(e.target.value)}
                    />
                    <div style={{ display: "flex", gap: "6px" }}>
                      <ButtonItem
                        layout="below"
                        onClick={handleCreateFolder}
                      >
                        Create
                      </ButtonItem>
                      <ButtonItem
                        layout="below"
                        onClick={() => {
                          setIsCreatingFolder(false);
                          setNewFolderName("");
                        }}
                      >
                        Cancel
                      </ButtonItem>
                    </div>
                  </div>
                )}

                <ButtonItem
                  layout="below"
                  onClick={() => handleSavePath(currentPath)}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", fontWeight: "bold", color: "#2ea043" }}>
                    <FaCheck size={12} /> Select Current Folder
                  </div>
                </ButtonItem>
              </div>
            )}

            {/* Go back option if path was already configured */}
            {isPathInitialized && (
              <div style={{ marginTop: "8px" }}>
                <ButtonItem
                  layout="below"
                  onClick={() => {
                    setIsConfiguringPath(false);
                    setPickerPath("root");
                  }}
                >
                  Cancel & Go Back
                </ButtonItem>
              </div>
            )}

            {isDev && (
              <div style={{ marginTop: "12px", borderTop: "1px solid #282e38", paddingTop: "12px" }}>
                <LogsSection 
                  showLogs={showLogs} 
                  logs={logs} 
                  logsError={logsError} 
                  onToggleLogs={handleToggleLogs} 
                />
              </div>
            )}
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title="Background Downloader">
      <PanelSectionRow>
        <div style={{ padding: "4px 0", fontSize: "14px", color: "#dcdcdc" }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: "8px" }}>
            <div style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              backgroundColor: getStatusColor(),
              marginRight: "8px"
            }} />
            <p style={{ margin: 0, fontWeight: "bold" }}>{statusMsg}</p>
          </div>
          
          <div style={{ 
            background: "#1a1f24", 
            padding: "12px", 
            borderRadius: "6px", 
            border: "1px solid #3a4450",
            marginBottom: "12px"
          }}>
            <span style={{ color: "#3aa3ff", fontWeight: "bold", display: "block", marginBottom: "4px", fontSize: "12px" }}>
              Remote Control Access URL:
            </span>
            <code style={{ fontSize: "14px", color: "#fff", fontFamily: "monospace", wordBreak: "break-all" }}>{ipUrl}</code>
          </div>

          {containerStatus === "running" && ipUrl !== "Initializing..." && (
            <div style={{ 
              display: "flex", 
              justifyContent: "center", 
              margin: "-4px auto 12px auto", 
              background: "#ffffff", 
              padding: "8px", 
              borderRadius: "6px", 
              width: "fit-content"
            }}>
              <QRCodeSVG value={ipUrl} size={110} bgColor="#ffffff" fgColor="#000000" level="M" />
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "12px" }}>
            <ButtonItem
              layout="below"
              onClick={handleStart}
              disabled={containerStatus === "running"}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}>
                <FaPlay size={12} /> Start Service
              </div>
            </ButtonItem>
            
            <ButtonItem
              layout="below"
              onClick={handleStop}
              disabled={containerStatus !== "running"}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}>
                <FaStop size={12} /> Stop Service
              </div>
            </ButtonItem>
            
            <ButtonItem
              layout="below"
              onClick={handleRestart}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}>
                <FaSync size={12} /> Restart Service
              </div>
            </ButtonItem>
          </div>

          <div style={{ fontSize: "12px", color: "#8a9aab", lineHeight: "1.4", background: "#161920", padding: "8px", borderRadius: "4px", border: "1px solid #282e38", marginBottom: "12px" }}>
            <span style={{ color: "#3aa3ff", fontWeight: "bold", display: "block", marginBottom: "4px" }}>Active Download Path:</span>
            <code style={{ display: "block", background: "#11141a", padding: "6px", borderRadius: "3px", marginBottom: "8px", wordBreak: "break-all" }}>{downloadPath}</code>
            <ButtonItem
              layout="below"
              onClick={() => setIsConfiguringPath(true)}
            >
              Change Download Folder
            </ButtonItem>
          </div>

          {isDev && (
            <LogsSection 
              showLogs={showLogs} 
              logs={logs} 
              logsError={logsError} 
              onToggleLogs={handleToggleLogs} 
            />
          )}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  return {
    name: "Decky Torrent",
    titleView: <div className={staticClasses.Title}>Decky Torrent</div>,
    content: <Content />,
    icon: <FaDownload />
  };
});
