import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Collapse,
  Divider,
  IconButton,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {
  ArrowBackRounded,
  DownloadOutlined,
  ExpandMoreRounded,
  PlayArrowRounded,
  SettingsOutlined,
} from "@mui/icons-material";
import { api, dateLabel, money } from "../api";
import { useWorkspace } from "../context";
import { ErrorMessage, Loading, PageHeading } from "./Common";
import NcrReportTable from "./NcrReportTable";
import type { LcrStressResults, StressResultRow } from "../types";

type View = "overview" | string;

export default function LcrStressOverview({
  asOf,
  onBack,
}: {
  asOf: string;
  onBack: () => void;
}) {
  const { entity } = useWorkspace();
  const [view, setView] = useState<View>("overview");
  const [severity, setSeverity] = useState("");
  const [auditOpen, setAuditOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const preview = useQuery({
    queryKey: ["lcr-stress-preview", entity?.slug, asOf],
    queryFn: () => api.lcrStressPreview(entity!.slug, asOf),
    enabled: !!entity && !!asOf,
  });
  const results = preview.data?.results;
  const scenarios = useMemo(() => {
    const unique = new Map<string, { id: string; name: string }>();
    (results?.results || []).forEach((row) =>
      unique.set(row.scenario_id, { id: row.scenario_id, name: row.scenario }),
    );
    return [...unique.values()];
  }, [results]);
  const scenarioRows = (results?.results || []).filter(
    (row) => row.scenario_id === view,
  );
  const activeSeverity = severity || scenarioRows[0]?.severity_id || "";
  const detail = scenarioRows.find((row) => row.severity_id === activeSeverity);
  const exportWorkbook = async () => {
    if (!entity || !asOf) return;
    setExporting(true);
    try {
      const run = await api.createLcrStressRun(entity.slug, asOf);
      window.location.assign(api.lcrStressExportUrl(entity.slug, run.id));
    } finally {
      setExporting(false);
    }
  };
  if (preview.isLoading) return <Loading />;
  return (
    <>
      <PageHeading
        eyebrow="REGULATORY LIQUIDITY · LCR"
        title="LCR Stress Testing"
        subtitle="Bank-format scenario overview, calculated from the selected LCR source snapshot."
        action={
          <Stack direction="row" gap={1} flexWrap="wrap">
            <Button
              variant="outlined"
              startIcon={<ArrowBackRounded />}
              onClick={onBack}
            >
              Back to LCR
            </Button>
            <Button
              variant="outlined"
              startIcon={<SettingsOutlined />}
              onClick={() => (window.location.hash = "#/lcr-stress")}
            >
              Scenario library
            </Button>
            <Button
              variant="contained"
              disabled={!results || exporting}
              startIcon={<DownloadOutlined />}
              onClick={exportWorkbook}
            >
              {exporting ? "Preparing export…" : "Export Excel"}
            </Button>
          </Stack>
        }
      />
      <ErrorMessage error={preview.error} />
      {!results ? (
        <Alert severity="info">
          No stress result is available for this snapshot.
        </Alert>
      ) : (
        <>
          <Stack
            direction={{ xs: "column", md: "row" }}
            gap={1.25}
            mb={2.5}
            alignItems={{ md: "center" }}
          >
            <Chip
              label={`Source date · ${dateLabel(preview.data!.as_of_date)}`}
              size="small"
            />
            <Chip
              label="Read-only preview · source data is unchanged"
              size="small"
              variant="outlined"
            />
            <Box flex={1} />
            <Typography variant="caption" color="text.secondary">
              View
            </Typography>
            <Select
              size="small"
              value={view}
              onChange={(event) => {
                setView(event.target.value);
                setSeverity("");
              }}
              sx={{ minWidth: 235 }}
            >
              <MenuItem value="overview">Overview</MenuItem>
              {scenarios.map((item) => (
                <MenuItem key={item.id} value={item.id}>
                  {item.name}
                </MenuItem>
              ))}
            </Select>
            {view !== "overview" && (
              <Select
                size="small"
                value={activeSeverity}
                onChange={(event) => setSeverity(event.target.value)}
                sx={{ minWidth: 125 }}
              >
                {scenarioRows.map((row) => (
                  <MenuItem key={row.severity_id} value={row.severity_id}>
                    {row.severity}
                  </MenuItem>
                ))}
              </Select>
            )}
          </Stack>
          {view === "overview" ? (
            <Overview
              results={results}
              entityName={entity?.name || "Jordan"}
              asOf={preview.data!.as_of_date}
            />
          ) : detail ? (
            <Detail
              row={detail}
              results={results}
              auditOpen={auditOpen}
              onAudit={() => setAuditOpen((value) => !value)}
            />
          ) : (
            <Alert severity="warning">
              Choose a scenario severity to inspect its impact.
            </Alert>
          )}
        </>
      )}
    </>
  );
}

function Overview({
  results,
  entityName,
  asOf,
}: {
  results: LcrStressResults;
  entityName: string;
  asOf: string;
}) {
  const rows = results.results;
  const groups = useMemo(() => {
    const output = new Map<string, StressResultRow[]>();
    rows.forEach((row) =>
      output.set(row.scenario_id, [
        ...(output.get(row.scenario_id) || []),
        row,
      ]),
    );
    return [...output.values()];
  }, [rows]);
  const descriptions = groups.map((group) => group[0]);
  return (
    <Stack gap={2.5}>
      <Card
        sx={{
          overflow: "hidden",
          border: "1px solid #C8D0DB",
          boxShadow: "0 9px 28px rgba(21,42,61,.09)",
        }}
      >
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "1.35fr 1fr" },
            bgcolor: "#183B57",
            color: "#fff",
            fontWeight: 800,
            textAlign: "center",
          }}
        >
          <Box py={0.8}>LCR ST {dateLabel(asOf)}</Box>
          <Box py={0.8}>{entityName}</Box>
        </Box>
        <Threshold label="Limit" value="100%" color="#D90000" text="#fff" />
        <Threshold label="Tolerance" value="120%" color="#F4B183" />
        <Threshold label="Risk Appetite" value=">120%" color="#70AD47" />
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr 1fr", sm: "1.35fr .65fr 1fr 1fr" },
            borderTop: "1px solid #C8D0DB",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          <Box
            sx={{
              gridColumn: { xs: "span 1", sm: "span 2" },
              p: 0.75,
              bgcolor: "#F6F7F9",
              fontWeight: 800,
              borderRight: { sm: "1px solid #C8D0DB" },
            }}
          >
            Baseline
          </Box>
          <Box
            sx={{
              p: 0.75,
              bgcolor: "#F6F7F9",
              fontWeight: 800,
              textAlign: "center",
              borderRight: { sm: "1px solid #C8D0DB" },
            }}
          >
            {pct(results.baseline.lcr)}
          </Box>
          <Box
            sx={{ display: { xs: "none", sm: "block" }, bgcolor: "#F6F7F9" }}
          />
        </Box>
        <TableContainer>
          <Table size="small" sx={{ minWidth: 610 }}>
            <TableHead>
              <TableRow sx={{ bgcolor: "#183B57" }}>
                {["Scenario", "Severity", "LCR ST", "Movement"].map((label) => (
                  <TableCell
                    key={label}
                    align={label === "Scenario" ? "left" : "center"}
                    sx={{
                      color: "#fff",
                      fontWeight: 800,
                      borderColor: "#48647D",
                    }}
                  >
                    {label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {groups.map((group) =>
                group.map((row, index) => (
                  <TableRow
                    key={`${row.scenario_id}-${row.severity_id}`}
                    sx={{ "& td": { borderColor: "#C8D0DB" } }}
                  >
                    {index === 0 && (
                      <TableCell
                        rowSpan={group.length}
                        sx={{
                          fontWeight: 750,
                          verticalAlign: "middle",
                          width: "40%",
                        }}
                      >
                        {row.scenario}
                      </TableCell>
                    )}
                    <TableCell align="center">{row.severity}</TableCell>
                    <TableCell
                      align="center"
                      sx={{
                        fontWeight: 800,
                        color: statusColor(row.risk_status),
                      }}
                    >
                      {pct(row.lcr)}
                    </TableCell>
                    <TableCell
                      align="center"
                      sx={{
                        fontWeight: 700,
                        color:
                          Number(row.movement) < 0
                            ? "error.main"
                            : "success.main",
                      }}
                    >
                      {signedPct(row.movement)}
                    </TableCell>
                  </TableRow>
                )),
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      <Card sx={{ overflow: "hidden" }}>
        <Box
          px={2.5}
          py={1.15}
          bgcolor="#183B57"
          color="#fff"
          display="grid"
          gridTemplateColumns={{ xs: "1fr", md: "minmax(240px,.9fr) 1.6fr" }}
          gap={2}
        >
          <Typography variant="subtitle2" fontWeight={800}>
            Scenario
          </Typography>
          <Typography variant="subtitle2" fontWeight={800}>
            Description
          </Typography>
        </Box>
        <Box>
          {[
            {
              scenario: "Baseline",
              description:
                "This scenario represents normal operating conditions without any stress.",
            },
            ...descriptions,
          ].map((row, index) => (
            <Box
              key={row.scenario}
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "1fr",
                  md: "minmax(240px,.9fr) 1.6fr",
                },
                borderTop: index ? "1px solid #C8D0DB" : 0,
              }}
            >
              <Box p={1.6} fontWeight={750}>
                {row.scenario}
              </Box>
              <Box
                p={1.6}
                borderLeft={{ md: "1px solid #C8D0DB" }}
                color="text.secondary"
              >
                {row.description}
              </Box>
            </Box>
          ))}
        </Box>
      </Card>
    </Stack>
  );
}
function Threshold({
  label,
  value,
  color,
  text = "#10233E",
}: {
  label: string;
  value: string;
  color: string;
  text?: string;
}) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "1.35fr 1fr" },
        bgcolor: color,
        color: text,
        fontWeight: 800,
        textAlign: "center",
        borderTop: "1px solid #fff",
      }}
    >
      <Box py={0.65}>{label}</Box>
      <Box py={0.65} borderLeft={{ sm: "1px solid rgba(255,255,255,.55)" }}>
        {value}
      </Box>
    </Box>
  );
}
function Detail({
  row,
  results,
  auditOpen,
  onAudit,
}: {
  row: StressResultRow;
  results: LcrStressResults;
  auditOpen: boolean;
  onAudit: () => void;
}) {
  const report = row.lcr_report;
  const audit = results.audit.filter(
    (item) => item.scenario === row.scenario && item.severity === row.severity,
  );
  const colour =
    row.risk_status === "Within Appetite"
      ? "success"
      : row.risk_status === "Tolerance"
        ? "warning"
        : "error";
  return (
    <Stack gap={2.5}>
      <Card
        sx={{
          p: { xs: 2, md: 2.5 },
          border: "1px solid #C9D7FC",
          boxShadow: "0 8px 24px rgba(40,76,154,.08)",
        }}
      >
        <Stack
          direction={{ xs: "column", md: "row" }}
          gap={2}
          alignItems={{ md: "center" }}
        >
          <Box flex={1}>
            <Typography
              variant="overline"
              color="primary.main"
              fontWeight={800}
            >
              SELECTED STRESS
            </Typography>
            <Typography variant="h5" fontWeight={750}>
              {row.scenario} · {row.severity}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {row.description}
            </Typography>
          </Box>
          <Chip label={row.risk_status} color={colour} />
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4,1fr)" },
            gap: 1.5,
          }}
        >
          <Kpi label="Baseline LCR" value={pct(results.baseline.lcr)} />
          <Kpi
            label="Stressed LCR"
            value={pct(row.lcr)}
            color={statusColor(row.risk_status)}
          />
          <Kpi
            label="Movement"
            value={signedPct(row.movement)}
            color={Number(row.movement) < 0 ? "error.main" : "success.main"}
          />
          <Kpi
            label="Net cash outflow"
            value={money(row.net_cash_outflow, report?.currency || "JOD")}
          />
        </Box>
      </Card>
      {report ? (
        <NcrReportTable report={report} />
      ) : (
        <Alert severity="info">
          This saved result predates element-level stress detail. Refresh the
          stress test to see the affected LCR elements.
        </Alert>
      )}
      <Card sx={{ overflow: "hidden" }}>
        <Box
          role="button"
          tabIndex={0}
          onClick={onAudit}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onAudit();
          }}
          sx={{
            p: 2,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 1,
            "&:hover": { bgcolor: "#F8FAFF" },
          }}
        >
          <Box flex={1}>
            <Typography fontWeight={750}>Rule-impact analysis</Typography>
            <Typography variant="caption" color="text.secondary">
              See which mapped source elements changed under this scenario.
            </Typography>
          </Box>
          <IconButton
            size="small"
            sx={{ transform: auditOpen ? "rotate(180deg)" : "none" }}
          >
            <ExpandMoreRounded />
          </IconButton>
        </Box>
        <Collapse in={auditOpen}>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Rule</TableCell>
                  <TableCell>Element</TableCell>
                  <TableCell align="right">Baseline</TableCell>
                  <TableCell align="right">Stressed</TableCell>
                  <TableCell align="right">Weighted change</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {audit.map((item, index) => (
                  <TableRow key={`${item.rule}-${index}`}>
                    <TableCell>{item.rule}</TableCell>
                    <TableCell>{item.element}</TableCell>
                    <TableCell align="right">{item.baseline_amount}</TableCell>
                    <TableCell align="right">{item.stressed_amount}</TableCell>
                    <TableCell align="right">{item.weighted_delta}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Collapse>
      </Card>
    </Stack>
  );
}
function Kpi({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <Box sx={{ p: 1.4, bgcolor: "#F8FAFC", borderRadius: 1.5 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" mt={0.25} sx={{ color, fontWeight: 800 }}>
        {value}
      </Typography>
    </Box>
  );
}
const pct = (value: string) => `${(Number(value) * 100).toFixed(1)}%`;
const signedPct = (value: string) =>
  `${Number(value) >= 0 ? "+" : ""}${(Number(value) * 100).toFixed(1)}%`;
const statusColor = (status: string) =>
  status === "Within Appetite"
    ? "success.main"
    : status === "Tolerance"
      ? "warning.main"
      : "error.main";
