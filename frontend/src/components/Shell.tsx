import { useState } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  Box,
  Stack,
  Typography,
  Drawer,
  Button,
  IconButton,
  Select,
  MenuItem,
  Chip,
  Avatar,
  Tooltip,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  Alert,
  LinearProgress,
  FormControl,
} from "@mui/material";
import {
  DashboardOutlined,
  AccountBalanceWalletOutlined,
  AddCircleOutlineRounded,
  HistoryRounded,
  AssessmentOutlined,
  ApartmentRounded,
  MenuRounded,
  HelpOutlineRounded,
  LogoutRounded,
  CodeRounded,
  LayersOutlined,
  CloseRounded,
  ExpandMoreRounded,
  ArrowOutwardRounded,
  TuneRounded,
  QueryStatsRounded,
  WarningAmberRounded,
} from "@mui/icons-material";
import { useWorkspace } from "../context";
import { csrf } from "../api";
const width = 242;
const workspaceLinks = [
  { path: "/", label: "Overview", icon: DashboardOutlined },
  {
    path: "/portfolio",
    label: "Portfolio",
    icon: AccountBalanceWalletOutlined,
  },
  { path: "/new", label: "New calculation", icon: AddCircleOutlineRounded },
  { path: "/runs", label: "Run history", icon: HistoryRounded },
  { path: "/results", label: "Results & controls", icon: AssessmentOutlined },
];
const regulatoryLinks = [
  { path: "/lcr", label: "LCR", icon: QueryStatsRounded },
  { path: "/nsfr", label: "NSFR", icon: QueryStatsRounded },
];
export default function Shell() {
  const { entity, entities, selectEntity, session, loading, error } =
    useWorkspace();
  const nav = useNavigate(),
    location = useLocation();
  const [mobile, setMobile] = useState(false),
    [help, setHelp] = useState(false),
    [modules, setModules] = useState(false);
  const sidebar = (
    <Box
      sx={{
        height: "100%",
        bgcolor: "#152A3D",
        color: "#D0DCE7",
        display: "flex",
        flexDirection: "column",
        px: 2.1,
        py: 3,
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        gap={1.3}
        sx={{ px: 1, mb: 4 }}
      >
        <Box
          sx={{
            width: 35,
            height: 35,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "3px",
            transform: "rotate(-5deg)",
          }}
        >
          {["#72CFBE", "#3E7196", "#4D8FAC", "#B4E2D5"].map((c) => (
            <Box key={c} sx={{ bgcolor: c, borderRadius: "3px" }} />
          ))}
        </Box>
        <Box>
          <Typography
            sx={{
              fontSize: 15,
              fontWeight: 650,
              color: "#fff",
              letterSpacing: -0.4,
            }}
          >
            ALM Workspace
          </Typography>
          <Typography
            sx={{ fontSize: 9, letterSpacing: 1.7, color: "#89A3B9", mt: 0.3 }}
          >
            RISK ANALYTICS PLATFORM
          </Typography>
        </Box>
      </Stack>
      <Box
        sx={{
          border: "1px solid #375062",
          borderRadius: 2,
          p: 1.4,
          mb: 3,
          bgcolor: "#1D354A",
        }}
      >
        <Stack direction="row" alignItems="center" gap={1.2}>
          <Box
            sx={{
              bgcolor: "#314E62",
              p: 0.8,
              borderRadius: 1.5,
              display: "flex",
            }}
          >
            <AccountBalanceWalletOutlined
              sx={{ fontSize: 18, color: "#92DACA" }}
            />
          </Box>
          <Box flex={1}>
            <Typography sx={{ fontSize: 12, fontWeight: 600, color: "#fff" }}>
              Liquidity cash flow
            </Typography>
            <Typography sx={{ fontSize: 10, color: "#A0B4C5" }}>
              Contractual + behavioural
            </Typography>
          </Box>
        </Stack>
      </Box>
      <Typography
        sx={{
          px: 1.5,
          mb: 1,
          fontSize: 9,
          letterSpacing: 1.7,
          color: "#7E9AAF",
          fontWeight: 650,
        }}
      >
        WORKSPACE
      </Typography>
      <Stack gap={0.55}>
        {workspaceLinks.map(({ path, label, icon: Icon }) => (
          <Box
            key={path}
            component={NavLink}
            to={path}
            end={path === "/"}
            onClick={() => setMobile(false)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.3,
              px: 1.5,
              py: 1.35,
              borderRadius: 1.5,
              color: "#AFC3D3",
              textDecoration: "none",
              fontSize: 12,
              fontWeight: 500,
              "&:hover": { bgcolor: "#213D53", color: "#fff" },
              "&.active": {
                bgcolor: "#2B4760",
                color: "#fff",
                boxShadow: "inset 3px 0 #72CFBE",
              },
              "& svg": { fontSize: 19 },
            }}
          >
            <Icon />
            {label}
          </Box>
        ))}
      </Stack>
      <Typography
        sx={{
          px: 1.5,
          mt: 3.5,
          mb: 1,
          fontSize: 9,
          letterSpacing: 1.7,
          color: "#7E9AAF",
          fontWeight: 650,
        }}
      >
        REGULATORY REPORTING
      </Typography>
      <Stack gap={0.55}>
        {regulatoryLinks.map(({ path, label, icon: Icon }) => (
          <Box
            key={path}
            component={NavLink}
            to={path}
            onClick={() => setMobile(false)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.3,
              px: 1.5,
              py: 1.35,
              borderRadius: 1.5,
              color: "#AFC3D3",
              textDecoration: "none",
              fontSize: 12,
              fontWeight: 500,
              "&:hover": { bgcolor: "#213D53", color: "#fff" },
              "&.active": {
                bgcolor: "#2B4760",
                color: "#fff",
                boxShadow: "inset 3px 0 #72CFBE",
              },
              "& svg": { fontSize: 19 },
            }}
          >
            <Icon />
            {label}
          </Box>
        ))}
      </Stack>
      <Typography
        sx={{
          px: 1.5,
          mt: 3.5,
          mb: 1,
          fontSize: 9,
          letterSpacing: 1.7,
          color: "#7E9AAF",
          fontWeight: 650,
        }}
      >
        PLATFORM
      </Typography>
      <Button
        component={NavLink}
        to="/entities"
        startIcon={<ApartmentRounded />}
        onClick={() => setMobile(false)}
        sx={{
          justifyContent: "flex-start",
          color: "#AFC3D3",
          px: 1.5,
          "&.active": { bgcolor: "#2B4760", color: "white" },
        }}
      >
        Entities
      </Button>
      <Button
        component={NavLink}
        to="/settings"
        startIcon={<TuneRounded />}
        onClick={() => setMobile(false)}
        sx={{
          justifyContent: "flex-start",
          color: "#AFC3D3",
          px: 1.5,
          mt: 0.5,
          "&.active": { bgcolor: "#2B4760", color: "white" },
        }}
      >
        Interest settings
      </Button>
      <Button
        component={NavLink}
        to="/assumptions"
        startIcon={<AssessmentOutlined />}
        onClick={() => setMobile(false)}
        sx={{
          justifyContent: "flex-start",
          color: "#AFC3D3",
          px: 1.5,
          mt: 0.5,
          "&.active": { bgcolor: "#2B4760", color: "white" },
        }}
      >
        Assumptions
      </Button>
      <Button
        startIcon={<LayersOutlined />}
        onClick={() => setModules(true)}
        sx={{
          justifyContent: "flex-start",
          color: "#AFC3D3",
          px: 1.5,
          mt: 0.5,
        }}
      >
        Future modules
        <Chip
          label="Planned"
          size="small"
          sx={{
            ml: "auto",
            bgcolor: "#284258",
            color: "#AAC1D1",
            fontSize: 8,
            height: 18,
          }}
        />
      </Button>
      <Box sx={{ flex: 1, minHeight: 40 }} />
      <Box sx={{ p: 1.8, borderRadius: 2, bgcolor: "#213B50", mb: 2 }}>
        <Typography sx={{ fontSize: 11, color: "#ECF2F7", fontWeight: 600 }}>
          Built to grow with you
        </Typography>
        <Typography
          sx={{ fontSize: 10, color: "#9AB2C5", mt: 0.7, lineHeight: 1.7 }}
        >
          One workspace for today’s liquidity analysis and tomorrow’s ALM
          capabilities.
        </Typography>
      </Box>
      <Button
        component="a"
        href="/api-docs"
        target="_blank"
        startIcon={<CodeRounded />}
        endIcon={<ArrowOutwardRounded sx={{ fontSize: 14 }} />}
        sx={{ color: "#96ADBF", justifyContent: "flex-start", fontSize: 11 }}
      >
        API documentation
      </Button>
      <Divider sx={{ borderColor: "#2C475D", my: 2 }} />
      <Stack direction="row" gap={1.2} alignItems="center">
        <Avatar
          sx={{ width: 31, height: 31, bgcolor: "#385B75", fontSize: 12 }}
        >
          {session?.username.slice(0, 2).toUpperCase()}
        </Avatar>
        <Box flex={1}>
          <Typography sx={{ fontSize: 11, fontWeight: 600, color: "#E6EEF4" }}>
            {session?.username}
          </Typography>
          <Typography sx={{ fontSize: 9, color: "#8DA6BB" }}>
            {session?.is_staff ? "Administrator" : "Analyst"}
          </Typography>
        </Box>
        <form action="/accounts/logout/" method="post">
          <input type="hidden" name="csrfmiddlewaretoken" value={csrf()} />
          <Tooltip title="Sign out">
            <IconButton
              type="submit"
              size="small"
              sx={{ color: "#AFC3D3" }}
              aria-label="Sign out"
            >
              <LogoutRounded sx={{ fontSize: 17 }} />
            </IconButton>
          </Tooltip>
        </form>
      </Stack>
    </Box>
  );
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Box component="nav" sx={{ width: { lg: width }, flexShrink: { lg: 0 } }}>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: "none", lg: "block" },
            "& .MuiDrawer-paper": { width, border: 0 },
          }}
        >
          {sidebar}
        </Drawer>
        <Drawer
          variant="temporary"
          open={mobile}
          onClose={() => setMobile(false)}
          sx={{ display: { lg: "none" }, "& .MuiDrawer-paper": { width } }}
        >
          {sidebar}
        </Drawer>
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box
          component="header"
          sx={{
            height: 76,
            bgcolor: "white",
            borderBottom: "1px solid",
            borderColor: "divider",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            px: { xs: 2, md: 4 },
            position: "sticky",
            top: 0,
            zIndex: 1100,
          }}
        >
          <Stack direction="row" gap={1.5} alignItems="center">
            <IconButton
              sx={{ display: { lg: "none" } }}
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <MenuRounded />
            </IconButton>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ display: { xs: "none", md: "block" } }}
            >
              Workspace{" "}
              <Box component="span" sx={{ mx: 1.5, color: "#C1CAD4" }}>
                /
              </Box>
              <Box
                component="span"
                sx={{ color: "text.primary", fontWeight: 500 }}
              >
                {location.pathname === "/entities" ? "Entities" : "Liquidity"}
              </Box>
            </Typography>
          </Stack>
          <Stack direction="row" gap={{ xs: 1, sm: 2 }} alignItems="center">
            <Box
              sx={{
                display: { xs: "none", md: "flex" },
                alignItems: "center",
                gap: 0.7,
              }}
            >
              <Box
                sx={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  bgcolor: "#23A686",
                }}
              />
              <Typography variant="caption" color="text.secondary">
                Local workspace
              </Typography>
            </Box>
            <FormControl size="small">
              <Select
                value={entity?.slug || ""}
                onChange={(e) => {
                  selectEntity(e.target.value);
                  nav("/");
                }}
                inputProps={{ "aria-label": "Select entity" }}
                sx={{ minWidth: { xs: 150, sm: 210 }, fontSize: 12 }}
                startAdornment={
                  <ApartmentRounded
                    sx={{ fontSize: 17, mr: 1, color: "text.secondary" }}
                  />
                }
                IconComponent={ExpandMoreRounded}
              >
                {entities.map((e) => (
                  <MenuItem key={e.slug} value={e.slug}>
                    {e.name}
                    {e.is_mock ? " · Mock" : ""}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tooltip title="Workspace guide">
              <IconButton
                aria-label="Open workspace guide"
                onClick={() => setHelp(true)}
              >
                <HelpOutlineRounded sx={{ fontSize: 21 }} />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>
        <Box
          component="main"
          sx={{ maxWidth: 1700, mx: "auto", p: { xs: 2, md: 4 } }}
        >
          {loading ? (
            <LinearProgress />
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : (
            <>
              <Stack direction="row" gap={1} alignItems="center" mb={2.8}>
                {entity?.is_mock && (
                  <Chip
                    size="small"
                    label="MOCK DATA"
                    sx={{
                      bgcolor: "#FFF0D6",
                      color: "#9E702A",
                      fontSize: 9,
                      letterSpacing: 0.5,
                    }}
                  />
                )}
                <Typography variant="caption" color="text.secondary">
                  {entity?.is_mock
                    ? "Synthetic portfolio for testing · No live bank data"
                    : "Entity workspace"}{" "}
                  <Box component="span" sx={{ mx: 1, color: "#C9D0DA" }}>
                    •
                  </Box>{" "}
                  Contractual cash flows only
                </Typography>
              </Stack>
              <Outlet key={entity?.slug} />
            </>
          )}
        </Box>
        <Box
          component="footer"
          sx={{
            px: { xs: 2, md: 4 },
            pb: 3,
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <Typography variant="caption" color="#99A5B4">
            ALM Workspace · Local prototype v0.3
          </Typography>
          <Typography
            variant="caption"
            color="#99A5B4"
            sx={{ display: { xs: "none", sm: "block" } }}
          >
            React · TypeScript · Material UI · Django
          </Typography>
        </Box>
      </Box>
      <Dialog
        open={help}
        onClose={() => setHelp(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          Find your way around
          <IconButton
            aria-label="Close guide"
            onClick={() => setHelp(false)}
            sx={{ float: "right" }}
          >
            <CloseRounded />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Stack gap={2}>
            {[
              [
                "1",
                "Review the portfolio",
                "Open Portfolio to inspect and edit saved contracts.",
              ],
              [
                "2",
                "Configure a calculation",
                "Choose the reporting date and time buckets in New calculation.",
              ],
              [
                "3",
                "Validate, then run",
                "Resolve data issues or explicitly accept exclusions before submitting.",
              ],
              [
                "4",
                "Explore the results",
                "Inspect the maturity ladder, contract schedules and reconciliation controls.",
              ],
            ].map(([n, t, d]) => (
              <Stack key={n} direction="row" gap={2}>
                <Avatar
                  sx={{
                    width: 30,
                    height: 30,
                    bgcolor: "#ECF1FE",
                    color: "primary.main",
                    fontSize: 12,
                  }}
                >
                  {n}
                </Avatar>
                <Box>
                  <Typography variant="subtitle2">{t}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {d}
                  </Typography>
                </Box>
              </Stack>
            ))}
            <Alert severity="info">
              Results show contractual gaps, not a behavioral forecast or an
              opening-cash-adjusted liquidity balance.
            </Alert>
          </Stack>
        </DialogContent>
      </Dialog>
      <Dialog
        open={modules}
        onClose={() => setModules(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          Room for the next capabilities
          <IconButton
            aria-label="Close modules"
            onClick={() => setModules(false)}
            sx={{ float: "right" }}
          >
            <CloseRounded />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            The module navigation can grow as these engines are built. These are
            planned areas, not available calculations.
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
            {[
              "IRRBB · EVE & NII",
              "Stress testing",
              "Balance-sheet simulation",
            ].map((x) => (
              <Box
                key={x}
                sx={{
                  p: 2,
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 2,
                }}
              >
                <LayersOutlined color="disabled" />
                <Typography variant="subtitle2" my={1}>
                  {x}
                </Typography>
                <Chip label="Planned" size="small" />
              </Box>
            ))}
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
}
