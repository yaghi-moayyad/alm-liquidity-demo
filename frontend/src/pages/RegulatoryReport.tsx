import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Collapse,
  Dialog,
  DialogContent,
  DialogTitle,
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
  ArrowForwardRounded,
  CloseRounded,
  DownloadOutlined,
  ExpandMoreRounded,
  HistoryRounded,
  TrendingDownRounded,
  TrendingUpRounded,
} from "@mui/icons-material";
import { useWorkspace } from "../context";
import { api, compact, dateLabel, money } from "../api";
import {
  ErrorMessage,
  Loading,
  PageHeading,
  SectionHead,
} from "../components/Common";
import NcrReportTable from "../components/NcrReportTable";
import NsfrReportTable from "../components/NsfrReportTable";
import LcrStressOverview from "../components/LcrStressOverview";
import type {
  NcrReport,
  NsfrReport,
  RegulatoryDriverDetail,
  RegulatoryMovement,
} from "../types";

type Kind = "lcr" | "nsfr";

const config = {
  lcr: {
    title: "LCR",
    subtitle:
      "Liquidity Coverage Ratio · familiar regulatory report with month-on-month explanation.",
    ratio: "LCR",
    primary: "High-quality liquid assets",
    secondary: "Net cash outflows",
  },
  nsfr: {
    title: "NSFR",
    subtitle:
      "Net Stable Funding Ratio · funding stability, maturity structure and month-on-month explanation.",
    ratio: "NSFR",
    primary: "Available stable funding",
    secondary: "Required stable funding",
  },
};

export default function RegulatoryReport({ kind }: { kind: Kind }) {
  const { entity } = useWorkspace();
  const [selected, setSelected] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [detailKey, setDetailKey] = useState("");
  const [stressMode, setStressMode] = useState(false);
  const copy = config[kind];
  const series = useQuery({
    queryKey: ["regulatory-series", entity?.slug, kind],
    queryFn: () => api.regulatorySeries(entity!.slug, kind),
    enabled: !!entity,
  });
  const movementHistory = useQuery({
    queryKey: ["regulatory-movement-history", entity?.slug, kind],
    queryFn: () => api.regulatoryMovementHistory(entity!.slug, kind),
    enabled: !!entity,
  });
  useEffect(() => {
    if (!selected && series.data?.points.length)
      setSelected(series.data.points.at(-1)!.as_of_date);
  }, [selected, series.data]);
  const report = useQuery<NcrReport | NsfrReport>({
    queryKey: ["regulatory-report", entity?.slug, kind, selected],
    queryFn: () =>
      kind === "lcr"
        ? api.lcrReport(entity!.slug, selected)
        : api.nsfrReport(entity!.slug, selected),
    enabled: !!entity && !!selected,
  });
  const drivers = useQuery({
    queryKey: ["regulatory-drivers", entity?.slug, kind, selected],
    queryFn: () => api.regulatoryDrivers(entity!.slug, kind, selected),
    enabled: !!entity && !!selected,
  });
  const driverDetail = useQuery<RegulatoryDriverDetail>({
    queryKey: [
      "regulatory-driver-detail",
      entity?.slug,
      kind,
      selected,
      detailKey,
    ],
    queryFn: () =>
      api.regulatoryDriverDetail(entity!.slug, kind, selected, detailKey),
    enabled: !!entity && !!selected && !!detailKey,
  });
  useEffect(() => {
    setDetailKey("");
  }, [selected, kind]);
  const points = useMemo(
    () =>
      series.data?.points.map((point) => ({
        ...point,
        label: dateLabel(point.as_of_date),
        ratio: Number(point.ratio) * 100,
        primary: Number(point.primary),
        secondary: Number(point.secondary),
      })) || [],
    [series.data],
  );

  if (kind === "lcr" && stressMode)
    return (
      <LcrStressOverview
        asOf={selected || entity?.as_of_date || ""}
        onBack={() => setStressMode(false)}
      />
    );

  if (series.isLoading || report.isLoading) return <Loading />;
  const item = report.data;
  const lcrItem = item as NcrReport | undefined;
  const nsfrItem = item as NsfrReport | undefined;
  const ratio = item
    ? kind === "lcr"
      ? Number(lcrItem!.lcr)
      : Number(nsfrItem!.nsfr)
    : 0;
  const first = points.find((point) => point.as_of_date === selected);
  const previous =
    points[
      Math.max(
        0,
        points.findIndex((point) => point.as_of_date === selected) - 1,
      )
    ];
  const delta = first && previous ? first.ratio - previous.ratio : 0;

  return (
    <>
      <PageHeading
        eyebrow="REGULATORY LIQUIDITY"
        title={copy.title}
        subtitle={copy.subtitle}
        action={
          <Stack direction="row" gap={1} alignItems="center">
            <Select
              size="small"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              sx={{ minWidth: 150 }}
            >
              {(series.data?.points || []).map((point) => (
                <MenuItem key={point.as_of_date} value={point.as_of_date}>
                  {dateLabel(point.as_of_date)}
                </MenuItem>
              ))}
            </Select>
            {kind === "lcr" && (
              <Button
                variant="outlined"
                startIcon={<TrendingDownRounded />}
                onClick={() => setStressMode(true)}
              >
                Stress testing
              </Button>
            )}
            {selected && (
              <Button
                component="a"
                href={api.regulatoryExportUrl(entity!.slug, kind, selected)}
                variant="contained"
                startIcon={<DownloadOutlined />}
              >
                Export Excel
              </Button>
            )}
          </Stack>
        }
      />
      <ErrorMessage
        error={
          series.error ||
          movementHistory.error ||
          report.error ||
          drivers.error ||
          driverDetail.error
        }
      />
      {item && (
        <>
          <Stack direction="row" gap={1} mb={2.5} flexWrap="wrap">
            <Chip
              label={
                item.as_of_date
                  ? `As of ${dateLabel(item.as_of_date)}`
                  : "Current"
              }
              size="small"
            />
            <Chip
              label={
                entity?.is_mock
                  ? "Jordan mock source data"
                  : "Mapped source data"
              }
              size="small"
              sx={{ bgcolor: "#FFF1DB", color: "#986A27" }}
            />
            <Chip label="Monthly snapshot" size="small" variant="outlined" />
          </Stack>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr 1fr", xl: "repeat(4,1fr)" },
              gap: 2,
              mb: 3,
            }}
          >
            <Metric
              label={copy.ratio}
              value={`${(ratio * 100).toFixed(1)}%`}
              note={
                delta
                  ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} pp versus previous snapshot`
                  : "First available comparison"
              }
              good={ratio >= 1}
            />
            <Metric
              label={copy.primary}
              value={money(
                kind === "lcr" ? lcrItem!.hqla : nsfrItem!.asf,
                item.currency,
              )}
              note="Calculated from mapped source positions"
            />
            <Metric
              label={copy.secondary}
              value={money(
                kind === "lcr" ? lcrItem!.net_cash_outflows : nsfrItem!.rsf,
                item.currency,
              )}
              note={
                kind === "lcr"
                  ? "30-day regulatory cash outflows"
                  : "Weighted stable-funding requirement"
              }
            />
            <Metric
              label="Selected source records"
              value={
                kind === "lcr"
                  ? String(lcrItem!.source_position_count)
                  : String(
                      nsfrItem!.rows.filter((row) => row.kind === "normal")
                        .length,
                    )
              }
              note="Saved with this month-end snapshot"
            />
          </Box>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: {
                xs: "1fr",
                xl: "minmax(0,1.75fr) minmax(330px,1fr)",
              },
              gap: 3,
              mb: 3,
            }}
          >
            <Card>
              <SectionHead
                title={`${copy.ratio} trend`}
                subtitle="Click any point to select that month and update the explanation."
              />
              <Box sx={{ height: 290, p: { xs: 1, md: 2 } }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={points}
                    onClick={(event) => {
                      const point = (event as any)?.activePayload?.[0]?.payload;
                      if (point?.as_of_date) setSelected(point.as_of_date);
                    }}
                    margin={{ top: 15, right: 22, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid
                      stroke="#E8EEF2"
                      strokeDasharray="3 4"
                      vertical={false}
                    />
                    <XAxis dataKey="label" axisLine={false} tickLine={false} />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickFormatter={(value) => `${value.toFixed(0)}%`}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      formatter={(value: any) => `${Number(value).toFixed(2)}%`}
                      labelFormatter={(label) => `As of ${label}`}
                    />
                    <Line
                      dataKey="ratio"
                      name={copy.ratio}
                      stroke="#315FD4"
                      strokeWidth={3}
                      dot={{ r: 4, fill: "#fff", strokeWidth: 2 }}
                      activeDot={{ r: 7 }}
                      type="monotone"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </Card>
            <DriverPanel
              kind={kind}
              drivers={drivers.data}
              currency={item.currency}
              onInspect={setDetailKey}
            />
          </Box>
          <MovementHistory
            kind={kind}
            items={movementHistory.data?.movements || []}
            selected={selected}
            open={historyOpen}
            onToggle={() => setHistoryOpen((open) => !open)}
            onSelect={(asOf) => {
              setSelected(asOf);
              setHistoryOpen(false);
            }}
          />
          <Card sx={{ mb: 3 }}>
            <SectionHead
              title={`${copy.primary} and ${copy.secondary}`}
              subtitle="Level movement across the selected history."
            />
            <Box sx={{ height: 250, p: { xs: 1, md: 2 } }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={points}
                  margin={{ top: 15, right: 20, left: 0, bottom: 5 }}
                >
                  <CartesianGrid
                    stroke="#E8EEF2"
                    strokeDasharray="3 4"
                    vertical={false}
                  />
                  <XAxis dataKey="label" axisLine={false} tickLine={false} />
                  <YAxis
                    tickFormatter={(value) => compact(value)}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(value: any) =>
                      money(Number(value), item.currency)
                    }
                  />
                  <Bar
                    dataKey="primary"
                    name={copy.primary}
                    fill="#239B85"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="secondary"
                    name={copy.secondary}
                    fill="#9EB4E8"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Card>
          {kind === "lcr" ? (
            <NcrReportTable report={lcrItem!} />
          ) : (
            <NsfrReportTable report={nsfrItem!} />
          )}
        </>
      )}
      <DriverDetailDialog
        open={!!detailKey}
        detail={driverDetail.data}
        loading={driverDetail.isLoading}
        onClose={() => setDetailKey("")}
      />
    </>
  );
}

function Metric({
  label,
  value,
  note,
  good,
}: {
  label: string;
  value: string;
  note: string;
  good?: boolean;
}) {
  return (
    <Card sx={{ p: 2.4 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant="h5"
        mt={1}
        color={
          good === undefined
            ? "text.primary"
            : good
              ? "success.main"
              : "error.main"
        }
      >
        {value}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        display="block"
        mt={0.75}
      >
        {note}
      </Typography>
    </Card>
  );
}

function MovementHistory({
  kind,
  items,
  selected,
  open,
  onToggle,
  onSelect,
}: {
  kind: Kind;
  items: RegulatoryMovement[];
  selected: string;
  open: boolean;
  onToggle: () => void;
  onSelect: (asOf: string) => void;
}) {
  const latest = items.at(-1);
  const trend = latest
    ? `${latest.delta_pp.startsWith("-") ? "Declined" : "Improved"} ${Math.abs(Number(latest.delta_pp)).toFixed(1)} pp in the latest month`
    : "A second snapshot will create the first comparison.";
  return (
    <Card
      sx={{
        mb: 3,
        overflow: "hidden",
        border: open ? "1px solid #C9D7FC" : undefined,
        boxShadow: open ? "0 8px 24px rgba(40,76,154,.09)" : undefined,
      }}
    >
      <Box
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onToggle();
        }}
        sx={{
          px: { xs: 2, md: 2.5 },
          py: 2,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 1.25,
          "&:hover": { bgcolor: "#F8FAFF" },
        }}
      >
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 2,
            bgcolor: "#EEF3FF",
            color: "#315FD4",
            display: "grid",
            placeItems: "center",
          }}
        >
          <HistoryRounded fontSize="small" />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle1" fontWeight={700}>
            Movement history
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {trend} · {items.length} month-on-month comparisons available
          </Typography>
        </Box>
        <Typography
          variant="caption"
          color="primary.main"
          fontWeight={700}
          sx={{ display: { xs: "none", sm: "block" } }}
        >
          {open ? "Hide history" : "Review prior movements"}
        </Typography>
        <IconButton
          size="small"
          aria-label={
            open ? "Collapse movement history" : "Expand movement history"
          }
          sx={{
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform .2s",
          }}
        >
          <ExpandMoreRounded />
        </IconButton>
      </Box>
      <Collapse in={open}>
        <TableContainer sx={{ borderTop: "1px solid #E8EEF2" }}>
          <Table
            size="small"
            aria-label={`${kind.toUpperCase()} movement history`}
          >
            <TableHead>
              <TableRow sx={{ bgcolor: "#F8FAFC" }}>
                <TableCell>Period</TableCell>
                <TableCell align="right">{kind.toUpperCase()}</TableCell>
                <TableCell align="right">Change</TableCell>
                <TableCell>Main driver</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {items
                .slice()
                .reverse()
                .map((item) => {
                  const active = item.as_of_date === selected;
                  const positive = Number(item.delta_pp) >= 0;
                  return (
                    <TableRow
                      key={item.as_of_date}
                      hover
                      selected={active}
                      onClick={() => onSelect(item.as_of_date)}
                      sx={{
                        cursor: "pointer",
                        "&.Mui-selected": { bgcolor: "#EEF3FF" },
                        "&.Mui-selected:hover": { bgcolor: "#E5EDFF" },
                      }}
                    >
                      <TableCell>
                        <Typography
                          variant="body2"
                          fontWeight={active ? 700 : 600}
                        >
                          {dateLabel(item.as_of_date)}{" "}
                          <Typography
                            component="span"
                            variant="caption"
                            color="text.secondary"
                          >
                            vs {dateLabel(item.comparison_date)}
                          </Typography>
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight={600}>
                          {(Number(item.ratio) * 100).toFixed(1)}%
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography
                          variant="body2"
                          fontWeight={700}
                          color={positive ? "success.main" : "error.main"}
                        >
                          {positive ? "+" : ""}
                          {Number(item.delta_pp).toFixed(1)} pp
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          noWrap
                          sx={{ maxWidth: { xs: 135, md: 290 } }}
                        >
                          {item.primary_driver?.label || "No material driver"}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          color={active ? "primary" : "default"}
                          aria-label={`Review ${dateLabel(item.as_of_date)} movement`}
                        >
                          <ArrowForwardRounded fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </TableContainer>
        <Box px={2.5} py={1.4} bgcolor="#F8FAFC">
          <Typography variant="caption" color="text.secondary">
            Choose a period to update the report and the full driver explanation
            above.
          </Typography>
        </Box>
      </Collapse>
    </Card>
  );
}

function DriverPanel({
  kind,
  drivers,
  currency,
  onInspect,
}: {
  kind: Kind;
  drivers: any;
  currency: string;
  onInspect: (key: string) => void;
}) {
  const values = drivers?.drivers || [];
  return (
    <Card sx={{ p: 2.5 }}>
      <Typography variant="h6">Why did it move?</Typography>
      <Typography variant="caption" color="text.secondary">
        {drivers?.comparison_date
          ? `Compared with ${dateLabel(drivers.comparison_date)}`
          : "Select a later month to compare."}
      </Typography>
      <Stack gap={1.8} mt={2.5}>
        {values.length ? (
          values.map((driver: any) => {
            const positive = Number(driver.ratio_impact) >= 0;
            return (
              <Box
                key={driver.label}
                role="button"
                tabIndex={0}
                onClick={() => onInspect(driver.detail_key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ")
                    onInspect(driver.detail_key);
                }}
                sx={{
                  p: 1.5,
                  bgcolor: "#F7F9FC",
                  borderRadius: 1.5,
                  cursor: "pointer",
                  border: "1px solid transparent",
                  transition: "all .18s",
                  "&:hover": {
                    bgcolor: "#F0F4FF",
                    borderColor: "#C9D7FC",
                    transform: "translateY(-1px)",
                  },
                }}
              >
                <Stack direction="row" gap={1} alignItems="center">
                  <Box
                    sx={{
                      color: positive ? "success.main" : "error.main",
                      display: "flex",
                    }}
                  >
                    {positive ? (
                      <TrendingUpRounded fontSize="small" />
                    ) : (
                      <TrendingDownRounded fontSize="small" />
                    )}
                  </Box>
                  <Typography variant="body2" fontWeight={600} flex={1}>
                    {driver.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="primary.main"
                    fontWeight={700}
                  >
                    Details
                  </Typography>
                  <ArrowForwardRounded fontSize="small" color="primary" />
                </Stack>
                <Stack direction="row" justifyContent="space-between" mt={1}>
                  <Typography variant="caption" color="text.secondary">
                    Movement: {money(driver.amount, currency)}
                  </Typography>
                  <Typography
                    variant="caption"
                    fontWeight={700}
                    color={positive ? "success.main" : "error.main"}
                  >
                    {positive ? "+" : ""}
                    {(Number(driver.ratio_impact) * 100).toFixed(2)} pp
                  </Typography>
                </Stack>
              </Box>
            );
          })
        ) : (
          <Alert severity="info">
            The first snapshot has no prior month for comparison.
          </Alert>
        )}
      </Stack>
      {drivers && (
        <Typography
          variant="caption"
          color="text.secondary"
          display="block"
          mt={2}
        >
          {drivers.reconciled
            ? "Drivers reconcile to the ratio movement."
            : "Driver reconciliation requires review."}
        </Typography>
      )}
    </Card>
  );
}

function DriverDetailDialog({
  open,
  detail,
  loading,
  onClose,
}: {
  open: boolean;
  detail?: RegulatoryDriverDetail;
  loading: boolean;
  onClose: () => void;
}) {
  const driverImpact = Number(detail?.driver_impact_pp || 0);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3, overflow: "hidden" } }}
    >
      <DialogTitle
        sx={{ px: { xs: 2.5, md: 3.5 }, py: 2.5, bgcolor: "#F7F9FE" }}
      >
        <Stack direction="row" alignItems="flex-start" gap={2}>
          <Box flex={1}>
            <Typography
              variant="overline"
              color="primary.main"
              fontWeight={800}
            >
              SOURCE-LEVEL MOVEMENT ANALYSIS
            </Typography>
            <Typography variant="h5" fontWeight={750}>
              What changed in {detail?.label || "this driver"}?
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              {detail?.comparison_date
                ? `${dateLabel(detail.comparison_date)} to ${dateLabel(detail.as_of_date)}`
                : "Loading comparison"}{" "}
              · calculated from the saved source snapshot
            </Typography>
          </Box>
          <IconButton onClick={onClose} aria-label="Close driver detail">
            <CloseRounded />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ p: 0 }}>
        {loading || !detail ? (
          <Box p={4}>
            <Typography color="text.secondary">
              Calculating source-level contribution bridge…
            </Typography>
          </Box>
        ) : (
          <>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              gap={1.5}
              px={{ xs: 2.5, md: 3.5 }}
              py={2.25}
            >
              <Metric
                label="Driver impact"
                value={`${driverImpact >= 0 ? "+" : ""}${driverImpact.toFixed(2)} pp`}
                note="Contribution to the ratio movement"
                good={driverImpact >= 0}
              />
              <Metric
                label="Total ratio movement"
                value={`${Number(detail.ratio_change_pp) >= 0 ? "+" : ""}${Number(detail.ratio_change_pp).toFixed(2)} pp`}
                note="Across all drivers"
              />
              <Metric
                label="Source status"
                value={detail.data_status}
                note={
                  detail.reconciled
                    ? "Component bridge reconciles"
                    : "Review reconciliation"
                }
              />
            </Stack>
            <Divider />
            <Box px={{ xs: 2.5, md: 3.5 }} pt={2.5} pb={1}>
              <Typography variant="subtitle1" fontWeight={700}>
                Underlying source elements
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Impact is shown in percentage points; share is the element’s
                signed contribution to the total{" "}
                {detail.report_type.toUpperCase()} movement.
              </Typography>
            </Box>
            <TableContainer sx={{ maxHeight: 470 }}>
              <Table
                stickyHeader
                size="small"
                aria-label="Source-level movement analysis"
              >
                <TableHead>
                  <TableRow>
                    <TableCell>Source element</TableCell>
                    <TableCell>Classification</TableCell>
                    <TableCell align="right">Prior balance</TableCell>
                    <TableCell align="right">Current balance</TableCell>
                    <TableCell align="right">Change</TableCell>
                    <TableCell align="right">Factor</TableCell>
                    <TableCell align="right">Impact</TableCell>
                    <TableCell align="right">Share</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detail.items.map((item) => {
                    const positive = Number(item.metric_impact_pp) >= 0;
                    return (
                      <TableRow key={item.id} hover>
                        <TableCell>
                          <Typography variant="body2" fontWeight={650}>
                            {item.source_line_item}
                          </Typography>
                          {item.code && (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              Report line {item.code}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={item.classification}
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="right">
                          {money(item.prior_balance, detail.currency)}
                        </TableCell>
                        <TableCell align="right">
                          {money(item.current_balance, detail.currency)}
                        </TableCell>
                        <TableCell align="right">
                          <Typography
                            variant="body2"
                            color={
                              Number(item.balance_change) >= 0
                                ? "success.main"
                                : "error.main"
                            }
                          >
                            {Number(item.balance_change) >= 0 ? "+" : ""}
                            {money(item.balance_change, detail.currency)}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          {item.factor || "—"}
                        </TableCell>
                        <TableCell align="right">
                          <Typography
                            variant="body2"
                            fontWeight={750}
                            color={positive ? "success.main" : "error.main"}
                          >
                            {positive ? "+" : ""}
                            {Number(item.metric_impact_pp).toFixed(2)} pp
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2" fontWeight={650}>
                            {item.share_of_movement === null
                              ? "—"
                              : `${Number(item.share_of_movement).toFixed(0)}%`}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
            <Box px={{ xs: 2.5, md: 3.5 }} py={2.25} bgcolor="#F8FAFC">
              <Typography variant="caption" color="text.secondary">
                The detail bridge is deterministic and based on balances and
                regulatory factors in the saved source snapshot. Positive and
                negative shares can offset; this is expected when drivers move
                in opposite directions.
              </Typography>
            </Box>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
