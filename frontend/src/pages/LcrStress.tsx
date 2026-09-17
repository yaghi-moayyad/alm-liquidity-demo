import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import {
  AddRounded,
  DeleteOutlineRounded,
  DownloadOutlined,
  EditOutlined,
  PlayArrowRounded,
  RestartAltRounded,
  WarningAmberRounded,
} from "@mui/icons-material";
import { useWorkspace } from "../context";
import { api, dateLabel, money } from "../api";
import { ErrorMessage, Loading, PageHeading } from "../components/Common";
import type {
  StressConfig,
  StressResultRow,
  StressRule,
  StressScenario,
  StressRun,
} from "../types";

const operations = [
  "rate_floor",
  "rate_cap",
  "rate_set",
  "rate_add",
  "rate_subtract",
  "rate_increase_pct",
  "rate_decrease_pct",
  "amount_haircut",
  "amount_decrease_pct",
  "amount_increase_pct",
  "amount_multiplier",
  "amount_add",
  "amount_subtract",
  "amount_set",
  "set_zero",
  "additional_outflow",
  "additional_inflow",
];
const targets = [
  "stable_deposits",
  "less_stable_deposits",
  "unused_facilities",
  "hqla_components",
  "credit_inflows",
  "outflows",
  "inflows",
  "all_input_elements",
  "manual_top_depositors",
];
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const emptyScenario = (): StressScenario => ({
  id: `custom_${Date.now()}`,
  name: "New liquidity stress",
  description: "Describe the source-driven stress scenario.",
  enabled: true,
  system_default: false,
  protected: false,
  levels: [
    { id: "moderate", label: "Moderate" },
    { id: "medium", label: "Medium" },
    { id: "severe", label: "Severe" },
  ],
  rules: [
    {
      name: "New rule",
      target: "less_stable_deposits",
      operation: "rate_floor",
      values: { moderate: 0.3, medium: 0.4, severe: 0.5 },
    },
  ],
});

export default function LcrStress() {
  const { entity } = useWorkspace();
  const [config, setConfig] = useState<StressConfig | null>(null);
  const [top, setTop] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<StressScenario | null>(null);
  const [run, setRun] = useState<StressRun | null>(null);
  const [saving, setSaving] = useState(false);
  const settings = useQuery({
    queryKey: ["lcr-stress-config", entity?.slug],
    queryFn: () => api.lcrStressConfig(entity!.slug),
    enabled: !!entity,
  });
  const series = useQuery({
    queryKey: ["regulatory-series", entity?.slug, "lcr"],
    queryFn: () => api.regulatorySeries(entity!.slug, "lcr"),
    enabled: !!entity,
  });
  const history = useQuery({
    queryKey: ["lcr-stress-runs", entity?.slug],
    queryFn: () => api.lcrStressRuns(entity!.slug),
    enabled: !!entity,
  });
  useEffect(() => {
    if (settings.data) {
      setConfig(copy(settings.data.configuration));
      setTop(settings.data.top_depositor_amounts);
    }
  }, [settings.data]);
  const asOf =
    series.data?.points.at(-1)?.as_of_date || entity?.as_of_date || "";
  const scenarios = config?.scenarios || [];
  const save = async () => {
    if (!entity || !config) return;
    setSaving(true);
    try {
      const saved = await api.saveLcrStressConfig(entity.slug, {
        configuration: config,
        top_depositor_amounts: top,
      });
      setConfig(copy(saved.configuration));
      setTop(saved.top_depositor_amounts);
      settings.refetch();
    } finally {
      setSaving(false);
    }
  };
  const execute = async () => {
    if (!entity || !asOf) return;
    await save();
    const created = await api.createLcrStressRun(entity.slug, asOf);
    setRun(created);
    history.refetch();
  };
  const updateScenario = (next: StressScenario) =>
    setConfig((current) =>
      current
        ? {
            ...current,
            scenarios: current.scenarios.map((s) =>
              s.id === next.id ? next : s,
            ),
          }
        : current,
    );
  const removeScenario = (id: string) =>
    setConfig((current) =>
      current
        ? {
            ...current,
            scenarios: current.scenarios.filter((s) => s.id !== id),
          }
        : current,
    );
  const restoreDefault = async (id: string) => {
    if (!entity) return;
    const saved = await api.restoreLcrStressDefault(entity.slug, id);
    setConfig(copy(saved.configuration));
    setTop(saved.top_depositor_amounts);
    settings.refetch();
  };
  const addScenario = () => {
    const next = emptyScenario();
    setConfig((current) =>
      current
        ? { ...current, scenarios: [...current.scenarios, next] }
        : current,
    );
    setSelected(next);
  };
  if (settings.isLoading || series.isLoading) return <Loading />;
  return (
    <>
      <PageHeading
        eyebrow="REGULATORY LIQUIDITY"
        title="LCR Stress Testing"
        subtitle="Central Bank scenario library and controlled custom stresses, calculated from the selected LCR source snapshot."
        action={
          <Stack direction="row" gap={1}>
            <Button
              variant="outlined"
              startIcon={<RestartAltRounded />}
              onClick={() =>
                settings.data && setConfig(copy(settings.data.configuration))
              }
            >
              Reset changes
            </Button>
            <Button
              variant="contained"
              disabled={!config || saving}
              startIcon={<PlayArrowRounded />}
              onClick={execute}
            >
              Run stress test
            </Button>
          </Stack>
        }
      />
      <ErrorMessage error={settings.error || series.error || history.error} />
      <Stack direction="row" gap={1} mb={3} flexWrap="wrap">
        <Chip label={`Source date · ${dateLabel(asOf)}`} size="small" />
        <Chip label="LCR limit · 100%" size="small" variant="outlined" />
        <Chip
          label="Risk appetite · ≥120%"
          size="small"
          color="success"
          variant="outlined"
        />
        <Chip
          label={`${scenarios.filter((s) => s.enabled).length} enabled scenarios`}
          size="small"
          variant="outlined"
        />
      </Stack>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            xl: "minmax(0,1.7fr) minmax(340px,1fr)",
          },
          gap: 3,
          mb: 3,
        }}
      >
        <Card sx={{ p: { xs: 2.5, md: 3 } }}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Box>
              <Typography variant="h6">Scenario library</Typography>
              <Typography variant="body2" color="text.secondary">
                Edit a shipped scenario, restore it before saving, or create a
                multi-rule custom scenario.
              </Typography>
            </Box>
            <Button
              startIcon={<AddRounded />}
              variant="outlined"
              onClick={addScenario}
            >
              New scenario
            </Button>
          </Stack>
          <Stack gap={1.2}>
            {scenarios.map((s) => (
              <ScenarioCard
                key={s.id}
                scenario={s}
                onEdit={() => setSelected(copy(s))}
                onToggle={() => updateScenario({ ...s, enabled: !s.enabled })}
                onDelete={
                  s.system_default ? undefined : () => removeScenario(s.id)
                }
              />
            ))}
          </Stack>
        </Card>
        <Card sx={{ p: { xs: 2.5, md: 3 }, height: "fit-content" }}>
          <Typography variant="h6">Run controls</Typography>
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            Top-depositor withdrawals are independent, 100% cash outflows,
            exactly as in the legacy engine.
          </Typography>
          <Divider sx={{ my: 2.25 }} />
          <Typography variant="subtitle2" mb={1.2}>
            Top-depositor inputs
          </Typography>
          <Stack gap={1.25}>
            {[
              ["moderate", "Top 1"],
              ["medium", "Top 3"],
              ["severe", "Top 5"],
            ].map(([id, label]) => (
              <TextField
                key={id}
                label={label}
                type="number"
                value={top[id] ?? 0}
                onChange={(e) =>
                  setTop({ ...top, [id]: Number(e.target.value) })
                }
                InputProps={{
                  endAdornment: (
                    <Typography variant="caption" color="text.secondary">
                      {entity?.base_currency}
                    </Typography>
                  ),
                }}
              />
            ))}
          </Stack>
          <Button
            fullWidth
            sx={{ mt: 2.25 }}
            variant="outlined"
            disabled={!config || saving}
            onClick={save}
          >
            Save scenario library
          </Button>
          <Alert severity="info" sx={{ mt: 2 }}>
            Each run starts from a clean source snapshot. Stress rules never
            alter the approved baseline.
          </Alert>
        </Card>
      </Box>
      <Results
        run={run}
        currency={entity?.base_currency || "JOD"}
        exportUrl={
          run && entity
            ? api.lcrStressExportUrl(entity.slug, run.id)
            : undefined
        }
      />
      <Card sx={{ mt: 3, p: 2.5 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          Recent stress-test runs
        </Typography>
        <TableContainer sx={{ mt: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Run date</TableCell>
                <TableCell>Source snapshot</TableCell>
                <TableCell align="right">Baseline LCR</TableCell>
                <TableCell align="right">Scenarios</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(history.data?.runs || []).map((item) => (
                <TableRow
                  key={item.id}
                  hover
                  sx={{ cursor: "pointer" }}
                  onClick={() =>
                    api.lcrStressRun(entity!.slug, item.id).then(setRun)
                  }
                >
                  <TableCell>
                    {new Date(item.created).toLocaleString()}
                  </TableCell>
                  <TableCell>{dateLabel(item.as_of_date)}</TableCell>
                  <TableCell align="right">
                    {(Number(item.baseline_lcr) * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell align="right">{item.scenario_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      <ScenarioBuilder
        scenario={selected}
        onClose={() => setSelected(null)}
        onSave={(next) => {
          updateScenario(next);
          setSelected(null);
        }}
        onRestore={restoreDefault}
      />
    </>
  );
}
function ScenarioCard({
  scenario,
  onEdit,
  onToggle,
  onDelete,
}: {
  scenario: StressScenario;
  onEdit: () => void;
  onToggle: () => void;
  onDelete?: () => void;
}) {
  return (
    <Box
      sx={{
        p: 1.75,
        border: "1px solid",
        borderColor: scenario.enabled ? "#D6E2FC" : "divider",
        borderRadius: 2,
        bgcolor: scenario.enabled ? "#FAFBFF" : "#FAFAFA",
        opacity: scenario.enabled ? 1 : 0.68,
      }}
    >
      <Stack direction="row" gap={1.5} alignItems="flex-start">
        <Box flex={1}>
          <Stack direction="row" gap={0.8} alignItems="center" flexWrap="wrap">
            <Typography variant="subtitle2" fontWeight={700}>
              {scenario.name}
            </Typography>
            <Chip
              label={
                scenario.system_default ? "Central Bank default" : "Custom"
              }
              size="small"
              color={scenario.system_default ? "primary" : "default"}
              variant="outlined"
            />
          </Stack>
          <Typography
            variant="caption"
            color="text.secondary"
            display="block"
            mt={0.45}
          >
            {scenario.description}
          </Typography>
          <Stack direction="row" gap={0.7} mt={1} flexWrap="wrap">
            {scenario.levels.map((level) => (
              <Chip key={level.id} size="small" label={level.label} />
            ))}
            <Chip
              size="small"
              variant="outlined"
              label={`${scenario.rules.length} rule${scenario.rules.length === 1 ? "" : "s"}`}
            />
          </Stack>
        </Box>
        <Stack direction="row" alignItems="center">
          <FormControlLabel
            control={<Switch checked={scenario.enabled} onChange={onToggle} />}
            label=""
          />
          <IconButton onClick={onEdit} aria-label={`Edit ${scenario.name}`}>
            <EditOutlined />
          </IconButton>
          {onDelete && (
            <IconButton
              color="error"
              onClick={onDelete}
              aria-label={`Delete ${scenario.name}`}
            >
              <DeleteOutlineRounded />
            </IconButton>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}
function Results({
  run,
  currency,
  exportUrl,
}: {
  run: StressRun | null;
  currency: string;
  exportUrl?: string;
}) {
  const rows = run?.results.results || [];
  if (!run)
    return (
      <Card
        sx={{
          p: 3,
          border: "1px dashed",
          borderColor: "divider",
          textAlign: "center",
        }}
      >
        <WarningAmberRounded color="disabled" />
        <Typography variant="h6" mt={1}>
          Ready to run the stress library
        </Typography>
        <Typography variant="body2" color="text.secondary">
          The result set will show baseline, all enabled scenarios, full LCR
          components, movement and risk status.
        </Typography>
      </Card>
    );
  return (
    <Card>
      <Box
        sx={{
          p: { xs: 2.5, md: 3 },
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
        >
          <Box>
            <Typography variant="h6">Stress-test results</Typography>
            <Typography variant="body2" color="text.secondary">
              Baseline LCR {(Number(run.results.baseline.lcr) * 100).toFixed(1)}
              % · {dateLabel(run.as_of_date)}
            </Typography>
          </Box>
          {exportUrl && (
            <Button
              component="a"
              href={exportUrl}
              variant="outlined"
              startIcon={<DownloadOutlined />}
            >
              Export Excel
            </Button>
          )}
        </Stack>
      </Box>
      <TableContainer sx={{ maxHeight: 510 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell>Scenario</TableCell>
              <TableCell>Severity</TableCell>
              <TableCell align="right">HQLA</TableCell>
              <TableCell align="right">Net outflow</TableCell>
              <TableCell align="right">LCR</TableCell>
              <TableCell align="right">Movement</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row: StressResultRow) => (
              <TableRow key={`${row.scenario_id}-${row.severity_id}`} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight={650}>
                    {row.scenario}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {row.type}
                  </Typography>
                </TableCell>
                <TableCell>{row.severity}</TableCell>
                <TableCell align="right">{money(row.hqla, currency)}</TableCell>
                <TableCell align="right">
                  {money(row.net_cash_outflow, currency)}
                </TableCell>
                <TableCell
                  align="right"
                  sx={{
                    fontWeight: 750,
                    color:
                      Number(row.lcr) < 1
                        ? "error.main"
                        : Number(row.lcr) < 1.2
                          ? "warning.main"
                          : "success.main",
                  }}
                >
                  {(Number(row.lcr) * 100).toFixed(1)}%
                </TableCell>
                <TableCell
                  align="right"
                  sx={{
                    color:
                      Number(row.movement) < 0 ? "error.main" : "success.main",
                  }}
                >
                  {Number(row.movement) >= 0 ? "+" : ""}
                  {(Number(row.movement) * 100).toFixed(1)} pp
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={
                      row.risk_status === "Below Limit"
                        ? "error"
                        : row.risk_status === "Tolerance"
                          ? "warning"
                          : "success"
                    }
                    label={row.risk_status}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Card>
  );
}
function ScenarioBuilder({
  scenario,
  onClose,
  onSave,
  onRestore,
}: {
  scenario: StressScenario | null;
  onClose: () => void;
  onSave: (scenario: StressScenario) => void;
  onRestore: (id: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<StressScenario | null>(null);
  useEffect(() => setDraft(scenario ? copy(scenario) : null), [scenario]);
  if (!draft) return null;
  const updateRule = (index: number, next: StressRule) =>
    setDraft({
      ...draft,
      rules: draft.rules.map((rule, i) => (i === index ? next : rule)),
    });
  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle>
        {draft.system_default
          ? "Edit Central Bank default"
          : "Scenario Builder"}
      </DialogTitle>
      <DialogContent>
        <Stack gap={2} pt={1}>
          <TextField
            label="Scenario name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <TextField
            label="Description"
            value={draft.description}
            multiline
            minRows={2}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <Typography variant="subtitle2">Severity labels</Typography>
          <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
            {draft.levels.map((level, index) => (
              <TextField
                key={level.id}
                fullWidth
                label={level.id}
                value={level.label}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    levels: draft.levels.map((item, i) =>
                      i === index ? { ...item, label: e.target.value } : item,
                    ),
                  })
                }
              />
            ))}
          </Stack>
          <Divider />
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
          >
            <Typography variant="subtitle2">Rules</Typography>
            <Button
              size="small"
              startIcon={<AddRounded />}
              onClick={() =>
                setDraft({
                  ...draft,
                  rules: [
                    ...draft.rules,
                    {
                      name: "New rule",
                      target: "outflows",
                      operation: "rate_floor",
                      values: { moderate: 0, medium: 0, severe: 0 },
                    },
                  ],
                })
              }
            >
              Add rule
            </Button>
          </Stack>
          {draft.rules.map((rule, index) => (
            <Box
              key={index}
              sx={{
                p: 1.5,
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 2,
              }}
            >
              <Stack gap={1}>
                <TextField
                  size="small"
                  label="Rule name"
                  value={rule.name}
                  onChange={(e) =>
                    updateRule(index, { ...rule, name: e.target.value })
                  }
                />
                <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
                  <Select
                    size="small"
                    fullWidth
                    value={rule.target}
                    onChange={(e) =>
                      updateRule(index, { ...rule, target: e.target.value })
                    }
                  >
                    {targets.map((target) => (
                      <MenuItem key={target} value={target}>
                        {target}
                      </MenuItem>
                    ))}
                  </Select>
                  <Select
                    size="small"
                    fullWidth
                    value={rule.operation}
                    onChange={(e) =>
                      updateRule(index, { ...rule, operation: e.target.value })
                    }
                  >
                    {operations.map((operation) => (
                      <MenuItem key={operation} value={operation}>
                        {operation}
                      </MenuItem>
                    ))}
                  </Select>
                </Stack>
                <TextField
                  size="small"
                  label="Specific source keys (optional)"
                  helperText="Comma-separated keys override the group target for this rule."
                  value={(rule.element_ids || []).join(", ")}
                  onChange={(e) =>
                    updateRule(index, {
                      ...rule,
                      element_ids: e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
                <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
                  {draft.levels.map((level) => (
                    <TextField
                      key={level.id}
                      size="small"
                      fullWidth
                      type="number"
                      label={level.label}
                      value={rule.values[level.id] ?? 0}
                      onChange={(e) =>
                        updateRule(index, {
                          ...rule,
                          values: {
                            ...rule.values,
                            [level.id]: Number(e.target.value),
                          },
                        })
                      }
                    />
                  ))}
                </Stack>
              </Stack>
            </Box>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        {draft.system_default && (
          <Button
            color="inherit"
            onClick={async () => {
              await onRestore(draft.id);
              onClose();
            }}
          >
            Restore shipped default
          </Button>
        )}
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => onSave(draft)}>
          Apply scenario
        </Button>
      </DialogActions>
    </Dialog>
  );
}
