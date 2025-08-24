import streamlit as st
import re
import time

# =========================================
# Session State – Initialization
# =========================================
initial_state = {
    'mode': 'Setup Grid',
    'setup_done': False,
    'grid': {},
    'homing': None,
    'width': 8,
    'height': 3,
    'num_bots': 4,           # configurable 1–10
    'last_num_bots': 4,      # to detect changes
    'bot_positions': {},     # {bot_idx: (xi, yi) | None}
    'steps': [],
    'current_bot': 1,
    'sim_step': 0,
    'frames': [],
    'traces': []
}
for k, v in initial_state.items():
    st.session_state.setdefault(k, v)

# temp inputs for setup
st.session_state.setdefault('temp_width', st.session_state.width)
st.session_state.setdefault('temp_height', st.session_state.height)
st.session_state.setdefault('temp_num_bots', st.session_state.num_bots)

# If requested bot count changes, reset dependent state
if st.session_state.temp_num_bots != st.session_state.last_num_bots:
    st.session_state.num_bots = int(st.session_state.temp_num_bots)
    st.session_state.last_num_bots = st.session_state.num_bots
    st.session_state.bot_positions = {i: None for i in range(1, st.session_state.num_bots + 1)}
    st.session_state.steps = []
    st.session_state.current_bot = 1
    st.session_state.sim_step = 0
    st.session_state.traces = [[] for _ in range(st.session_state.num_bots)]

# Ensure bot_positions matches num_bots
if len(st.session_state.bot_positions) != st.session_state.num_bots:
    st.session_state.bot_positions = {i: None for i in range(1, st.session_state.num_bots + 1)}

# =========================================
# Title & Mode
# =========================================
st.title(f"{st.session_state.num_bots}-Bot Grid Planner & Simulator")
mode = st.sidebar.selectbox("Mode:", ['Setup Grid', 'Place Bots', 'Import Steps', 'Simulate Steps'], key='mode')

# =========================================
# Helpers
# =========================================
def init_grid():
    """Apply temp_* inputs and reset state."""
    st.session_state.width = int(st.session_state.temp_width)
    st.session_state.height = int(st.session_state.temp_height)
    st.session_state.num_bots = int(st.session_state.temp_num_bots)
    st.session_state.last_num_bots = st.session_state.num_bots

    st.session_state.grid = {
        (xi, yi): False
        for xi in range(st.session_state.width)
        for yi in range(st.session_state.height)
    }
    st.session_state.homing = None
    st.session_state.bot_positions = {i: None for i in range(1, st.session_state.num_bots + 1)}
    st.session_state.steps = []
    st.session_state.current_bot = 1
    st.session_state.sim_step = 0
    st.session_state.frames = []
    st.session_state.traces = [[] for _ in range(st.session_state.num_bots)]
    st.session_state.setup_done = True

def controller_maps():
    """Create forward/back transforms between grid and controller coordinates."""
    w = st.session_state.width
    h = st.session_state.height
    hx, hy = st.session_state.homing
    xmap = {xi: (hx - xi) * 10 for xi in range(w)}
    ymap = {yi: (hy - yi) * 10 for yi in range(h)}
    inv_x = {v: k for k, v in xmap.items()}
    inv_y = {v: k for k, v in ymap.items()}
    return xmap, ymap, inv_x, inv_y

# =========================================
# Setup Grid
# =========================================
if mode == 'Setup Grid':
    st.subheader("Grid Setup")
    st.number_input("Width (max 10)", min_value=1, max_value=10, value=st.session_state.temp_width, key='temp_width')
    st.number_input("Height (max 10)", min_value=1, max_value=10, value=st.session_state.temp_height, key='temp_height')
    st.number_input("Bots (1–10)", min_value=1, max_value=10, value=st.session_state.temp_num_bots, key='temp_num_bots')

    if st.button("Init Grid"):
        init_grid()

    if st.session_state.setup_done:
        w = st.session_state.width
        h = st.session_state.height
        cols = st.columns(w)
        for yi in range(h - 1, -1, -1):
            for xi in range(w):
                free = st.session_state.grid[(xi, yi)]
                is_home = (st.session_state.homing == (xi, yi))
                label = 'H' if is_home else ('·' if free else 'X')

                def toggle(xi=xi, yi=yi, free=free, is_home=is_home):
                    # Click logic: first click on X -> make cell free,
                    # then on a free cell -> toggle Home marker.
                    if not free:
                        st.session_state.grid[(xi, yi)] = True
                    else:
                        st.session_state.homing = None if is_home else (xi, yi)

                cols[xi].button(label, key=f'setup_{xi}_{yi}', on_click=toggle)

        st.write("Click **X** to make a cell free, then click **·** to set **Home (H)**.")

# =========================================
# Place Bots
# =========================================
elif mode == 'Place Bots' and st.session_state.setup_done:
    w = st.session_state.width
    h = st.session_state.height
    home = st.session_state.homing
    num_bots = st.session_state.num_bots

    if home is None:
        st.warning("Please set a homing cell in Setup Grid first.")
    else:
        hx, hy = home
        xmap = {xi: (hx - xi) * 10 for xi in range(w)}
        ymap = {yi: (hy - yi) * 10 for yi in range(h)}

        st.subheader(f"Place bots (1–{num_bots} cycles automatically), then click “Add Step”.")
        st.write(f"Next Bot: **{st.session_state.current_bot}**")

        cols = st.columns(w)
        for yi in range(h - 1, -1, -1):
            for xi in range(w):
                free = st.session_state.grid[(xi, yi)]  # free = traversable (not blocked)
                occs = [b for b, p in st.session_state.bot_positions.items() if p == (xi, yi)]
                is_home = (xi, yi) == home

                # Label shows occupants if any (e.g., "1,3"), otherwise H / · / X
                label = ','.join(map(str, occs)) if occs else ('H' if is_home else ('·' if free else 'X'))

                def place_bot(xi=xi, yi=yi, free=free):
                    # Allow overlapping: only disallow blocked cells
                    if free:
                        b = st.session_state.current_bot
                        st.session_state.bot_positions[b] = (xi, yi)
                        st.session_state.current_bot = (b % num_bots) + 1

                # IMPORTANT CHANGE: button disabled ONLY if the cell is blocked, not if occupied
                cols[xi].button(label, key=f'bot_{xi}_{yi}', disabled=(not free), on_click=place_bot)

        placed = {b: (xmap[p[0]], ymap[p[1]]) for b, p in st.session_state.bot_positions.items() if p}
        st.write("Current positions (controller coordinates):", placed)

        if len(placed) == num_bots:
            def add_step():
                coords = []
                for b in range(1, num_bots + 1):
                    xi, yi = st.session_state.bot_positions[b]
                    coords += [xmap[xi], ymap[yi]]
                st.session_state.steps.append(coords)
                st.session_state.current_bot = 1
                st.session_state.sim_step = 0
            st.button("Add Step", on_click=add_step)

        if st.session_state.steps:
            st.subheader("Generated code steps (hover to copy)")
            code = "\n".join(f"mvc.move({', '.join(map(str, s))})" for s in st.session_state.steps)
            st.code(code, language='python')

# =========================================
# Import Steps
# =========================================
elif mode == 'Import Steps' and st.session_state.setup_done:
    num_bots = st.session_state.num_bots
    st.subheader("Import MVC steps (alternative to placing)")
    st.caption(f"Expected lines like:  mvc.move(x1, y1, x2, y2, …, x{num_bots}, y{num_bots})")

    text = st.text_area("Paste mvc.move(...) lines here")

    if st.button("Parse Steps"):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        parsed = []
        bad = []
        for l in lines:
            m = re.match(r'^\s*mvc\.move\(([^)]+)\)\s*$', l)
            if not m:
                bad.append(l)
                continue
            nums = [n.strip() for n in m.group(1).split(',')]
            if len(nums) != 2 * num_bots:
                bad.append(l)
                continue
            try:
                parsed.append([int(n) for n in nums])
            except ValueError:
                bad.append(l)

        if parsed:
            st.session_state.steps = parsed
            st.session_state.sim_step = 0
            st.success(f"Parsed {len(parsed)} step(s).")
            if bad:
                st.warning(f"Skipped {len(bad)} line(s) (format/count).")
        else:
            st.error("No valid mvc.move(...) lines found.")

# =========================================
# Simulate Steps
# =========================================
elif mode == 'Simulate Steps' and st.session_state.steps:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    w = st.session_state.width
    h = st.session_state.height
    home = st.session_state.homing
    num_bots = st.session_state.num_bots

    if home is None:
        st.warning("Please set a homing cell in Setup Grid first.")
    else:
        # Build maps
        xmap, ymap, inv_x, inv_y = controller_maps()

        # Precompute paths between steps
        steps_list = st.session_state.steps
        paths = []  # paths[i][b] -> list of (xi, yi) inside step i
        for i in range(len(steps_list)):
            curr = steps_list[i]
            prev = steps_list[i - 1] if i > 0 else curr
            bot_paths = []
            for b in range(num_bots):
                cx0, cy0 = prev[2 * b], prev[2 * b + 1]
                cx1, cy1 = curr[2 * b], curr[2 * b + 1]
                try:
                    xi0, yi0 = inv_x[cx0], inv_y[cy0]
                    xi1, yi1 = inv_x[cx1], inv_y[cy1]
                except KeyError:
                    bot_paths.append([])
                    continue
                dx, dy = xi1 - xi0, yi1 - yi0
                steps_n = int(max(abs(dx), abs(dy)))
                path = []
                for s in range(steps_n + 1):
                    x_pos = xi0 + (dx / steps_n) * s if steps_n else xi0
                    y_pos = yi0 + (dy / steps_n) * s if steps_n else yi0
                    path.append((x_pos, y_pos))
                bot_paths.append(path)
            paths.append(bot_paths)

        # Flatten frames
        frames = []
        for bot_paths in paths:
            step_frames = max([len(bp) for bp in bot_paths if bp] or [0])
            for step_idx in range(step_frames):
                pos_list = []
                for b in range(num_bots):
                    path = bot_paths[b]
                    if not path:
                        pos_list.append(None)
                        continue
                    idx = step_idx if step_idx < len(path) else len(path) - 1
                    pos_list.append(path[idx])
                frames.append(pos_list)

        st.session_state.frames = frames
        if (not st.session_state.traces) or len(st.session_state.traces) != num_bots:
            st.session_state.traces = [[] for _ in range(num_bots)]
        st.session_state.setdefault('sim_step', 0)

        placeholder = st.empty()
        hx, hy = home

        def draw_frame(idx: int):
            if idx < 0 or idx >= len(st.session_state.frames):
                return
            positions = st.session_state.frames[idx]
            fig, ax = plt.subplots()

            # Draw grid
            for xi in range(w):
                for yi in range(h):
                    cell_free = st.session_state.grid[(xi, yi)]
                    color = 'white' if cell_free else 'black'
                    rect = patches.Rectangle((xi - 0.5, yi - 0.5), 1, 1,
                                             facecolor=color, edgecolor='gray')
                    ax.add_patch(rect)

            # Homing outline
            home_rect = patches.Rectangle((hx - 0.5, hy - 0.5), 1, 1,
                                          facecolor='none', edgecolor='red', linewidth=2)
            ax.add_patch(home_rect)

            # Colors for up to 10 bots
            palette = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
            colors = palette[:num_bots]

            # Traces & bots
            for b, pos in enumerate(positions):
                if pos is None:
                    continue
                xdraw, ydraw = pos
                while len(st.session_state.traces) <= b:
                    st.session_state.traces.append([])
                st.session_state.traces[b].append((xdraw, ydraw))

                xs = [p[0] for p in st.session_state.traces[b]]
                ys = [p[1] for p in st.session_state.traces[b]]

                ax.plot(xs, ys, linewidth=2, alpha=0.6, color=colors[b])
                ax.scatter(xdraw, ydraw, s=300, marker='o', c=colors[b])
                ax.text(xdraw, ydraw, str(b + 1), color='white', ha='center', va='center', fontsize=12)

            ax.set_xticks(range(w))
            ax.set_yticks(range(h))
            ax.set_xticklabels([xmap[xi] for xi in range(w)])
            ax.set_yticklabels([ymap[yi] for yi in range(h)])
            ax.set_xlim(-0.5, w - 0.5)
            ax.set_ylim(-0.5, h - 0.5)
            ax.set_aspect('equal')
            placeholder.pyplot(fig)

        # Controls
        colA, colB, colC = st.columns(3)
        if colA.button('Play Animation'):
            st.session_state.traces = [[] for _ in range(num_bots)]
            for i in range(st.session_state.sim_step, len(st.session_state.frames)):
                draw_frame(i)
                time.sleep(0.5)
                st.session_state.sim_step = i + 1
        if colB.button('Next Frame'):
            if st.session_state.sim_step < len(st.session_state.frames):
                draw_frame(st.session_state.sim_step)
                st.session_state.sim_step += 1
            else:
                st.info('Simulation finished')
        if colC.button('Reset Simulation'):
            st.session_state.traces = [[] for _ in range(num_bots)]
            st.session_state.sim_step = 0
            if st.session_state.frames:
                draw_frame(0)

else:
    if mode == 'Simulate Steps':
        st.info("No steps available. Use 'Place Bots' or 'Import Steps'.")
