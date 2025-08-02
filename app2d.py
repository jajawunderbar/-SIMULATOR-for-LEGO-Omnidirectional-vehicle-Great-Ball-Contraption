import streamlit as st
import re

# --- Session State Initialization ---
initial_state = {
    'mode': 'Setup Grid',
    'setup_done': False,
    'grid': {},
    'homing': None,
    'width': 8,
    'height': 3,
    'bot_positions': {i: None for i in range(1,5)},
    'steps': [],
    'current_bot': 1,
    'sim_step': 0
}
for key, default in initial_state.items():
    st.session_state.setdefault(key, default)
# temp inputs
st.session_state.setdefault('temp_width', st.session_state.width)
st.session_state.setdefault('temp_height', st.session_state.height)

st.title("4-Bot Grid Planner & Simulator")
mode = st.sidebar.selectbox(
    "Mode:", ['Setup Grid', 'Place Bots', 'Import Steps', 'Simulate Steps'],
    key='mode'
)

# --- Grid Initialization ---
def init_grid():
    st.session_state.width = st.session_state.temp_width
    st.session_state.height = st.session_state.temp_height
    st.session_state.grid = {
        (xi, yi): False
        for xi in range(st.session_state.width)
        for yi in range(st.session_state.height)
    }
    st.session_state.homing = None
    st.session_state.bot_positions = {i: None for i in range(1,5)}
    st.session_state.steps = []
    st.session_state.current_bot = 1
    st.session_state.sim_step = 0
    st.session_state.setup_done = True

# --- Setup Grid Mode ---
if mode == 'Setup Grid':
    st.subheader("Grid Setup")
    st.number_input(
        "Width (max 10)", min_value=1, max_value=10,
        value=st.session_state.temp_width, key='temp_width'
    )
    st.number_input(
        "Height (max 10)", min_value=1, max_value=10,
        value=st.session_state.temp_height, key='temp_height'
    )
    if st.button("Init Grid"):
        init_grid()

    if st.session_state.setup_done:
        w = st.session_state.width
        h = st.session_state.height
        cols = st.columns(w)
        for yi in range(h-1, -1, -1):
            for xi in range(w):
                free = st.session_state.grid[(xi, yi)]
                is_home = (st.session_state.homing == (xi, yi))
                label = 'H' if is_home else ('·' if free else 'X')
                def toggle(xi=xi, yi=yi, free=free, is_home=is_home):
                    if not free:
                        st.session_state.grid[(xi, yi)] = True
                    else:
                        st.session_state.homing = None if is_home else (xi, yi)
                cols[xi].button(
                    label,
                    key=f'setup_{xi}_{yi}',
                    on_click=toggle
                )
        st.write("Click X to mark free, then · to set home (H) (two clicks), then next step in menu left.")

# --- Place Bots Mode ---
elif mode == 'Place Bots' and st.session_state.setup_done:
    w = st.session_state.width
    h = st.session_state.height
    home = st.session_state.homing
    if home is None:
        st.warning("Please set homing point in Setup Grid.")
    else:
        hx, hy = home
        xmap = {xi: (hx - xi) * 10 for xi in range(w)}
        ymap = {yi: (hy - yi) * 10 for yi in range(h)}
        st.subheader("Place Bots, 1-4 rolling automatically, then scroll down and -add step- and again 1-4")
        st.write(f"Next Bot: {st.session_state.current_bot}")
        cols = st.columns(w)
        for yi in range(h-1, -1, -1):
            for xi in range(w):
                free = st.session_state.grid[(xi, yi)]
                occ = next((b for b,p in st.session_state.bot_positions.items() if p==(xi,yi)), None)
                is_home = (xi, yi)==home
                label = str(occ) if occ else ('H' if is_home else ('·' if free else 'X'))
                def place_bot(xi=xi, yi=yi, free=free):
                    if free:
                        b=st.session_state.current_bot
                        st.session_state.bot_positions[b]=(xi,yi)
                        st.session_state.current_bot = 1 if b==4 else b+1
                cols[xi].button(label, key=f'bot_{xi}_{yi}', disabled=not free, on_click=place_bot)
        placed = {b:(xmap[p[0]],ymap[p[1]]) for b,p in st.session_state.bot_positions.items() if p}
        st.write("Current Positions:", placed)
        if len(placed)==4:
            def add_step():
                coords=[]
                for b in range(1,5):
                    xi,yi=st.session_state.bot_positions[b]
                    coords += [xmap[xi], ymap[yi]]
                st.session_state.steps.append(coords)
                st.session_state.current_bot=1
                st.session_state.sim_step=0
            st.button("Add Step", on_click=add_step)
        if st.session_state.steps:
            st.subheader("Generated Code Steps (mouse over to copy)")
            code="\n".join(f"mvc.move({', '.join(map(str,s))})" for s in st.session_state.steps)
            st.code(code,language='python')

# --- Import Steps Mode ---
elif mode=='Import Steps' and st.session_state.setup_done:
    st.subheader("Import MVC Steps (as alternative to place them)")
    text=st.text_area("Paste mvc.move(...) lines here")
    if st.button("Parse Steps"):
        lines=[l.strip() for l in text.splitlines() if l.strip()]
        parsed=[]
        for l in lines:
            m=re.match(r'mvc\.move\(([^)]+)\)',l)
            if m: parsed.append([int(n) for n in m.group(1).split(',')])
        if parsed:
            st.session_state.steps=parsed
            st.success(f"Parsed {len(parsed)} steps.")
            st.session_state.sim_step=0
        else:
            st.error("No valid mvc.move() lines found.")

# --- Simulation Mode ---
elif mode == 'Simulate Steps' and st.session_state.steps:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import time
    w = st.session_state.width
    h = st.session_state.height
    home = st.session_state.homing
    if home is None:
        st.warning("Please set homing point in Setup Grid.")
    else:
        # map coords
        hx, hy = home
        xmap = {xi: (hx - xi) * 10 for xi in range(w)}
        ymap = {yi: (hy - yi) * 10 for yi in range(h)}
        inv_x = {v: k for k, v in xmap.items()}
        inv_y = {v: k for k, v in ymap.items()}

        # Get controller coordinate steps and precompute interpolated paths
        steps_list = st.session_state.steps
        # ``paths[i][b]`` holds a list of (xi, yi) positions for bot ``b`` as
        # it moves between step ``i-1`` and ``i``.  Empty lists mean the bot
        # was off-grid and is skipped in the animation.
        paths: list[list[list[tuple[float, float]]]] = []
        for i in range(len(steps_list)):
            curr = steps_list[i]
            prev = steps_list[i - 1] if i > 0 else curr
            bot_paths: list[list[tuple[float, float]]] = []
            for b in range(4):
                cx0, cy0 = prev[2 * b], prev[2 * b + 1]
                cx1, cy1 = curr[2 * b], curr[2 * b + 1]
                # Convert controller coordinates back to grid indices
                try:
                    xi0, yi0 = inv_x[cx0], inv_y[cy0]
                    xi1, yi1 = inv_x[cx1], inv_y[cy1]
                except KeyError:
                    # Skip bots with coordinates outside of the grid
                    bot_paths.append([])
                    continue
                dx, dy = xi1 - xi0, yi1 - yi0
                steps_n = int(max(abs(dx), abs(dy)))
                # Build an interpolated path; record at least one point even
                # when ``steps_n`` is zero so that the current location is
                # available for drawing
                path: list[tuple[float, float]] = []
                for s in range(steps_n + 1):
                    # Linear interpolation between start and end cells
                    x_pos = xi0 + (dx / steps_n) * s if steps_n else xi0
                    y_pos = yi0 + (dy / steps_n) * s if steps_n else yi0
                    path.append((x_pos, y_pos))
                bot_paths.append(path)
            paths.append(bot_paths)

        # Precompute a flat list of frame positions for all bots across all steps.
        # Each entry in ``frames`` is a list of length 4, containing either a
        # tuple of (xi, yi) coordinates for a bot or ``None`` if the bot is off-grid.
        # List of frame positions for all bots; each entry contains 4 items
        frames = []
        for bot_paths in paths:
            # Determine the number of intermediate frames required for this step
            step_frames = max([len(bp) for bp in bot_paths if bp] or [0])
            for step_idx in range(step_frames):
                pos_list = []
                for b in range(4):
                    path = bot_paths[b]
                    if not path:
                        pos_list.append(None)
                        continue
                    idx = step_idx if step_idx < len(path) else len(path) - 1
                    pos_list.append(path[idx])
                frames.append(pos_list)

        # Store frames and traces in the session state so that manual stepping works
        st.session_state.frames = frames
        if 'traces' not in st.session_state:
            st.session_state.traces = [[] for _ in range(4)]
        # Ensure the simulation step counter exists
        st.session_state.setdefault('sim_step', 0)

        # Create a placeholder for the current frame
        placeholder = st.empty()

        def draw_frame(idx: int) -> None:
            """Draw a single simulation frame and update trace history."""
            # Bounds check
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
            # Draw homing cell outline
            home_rect = patches.Rectangle((hx - 0.5, hy - 0.5), 1, 1,
                                          facecolor='none', edgecolor='red', linewidth=2)
            ax.add_patch(home_rect)
            colors = ['red', 'blue', 'green', 'yellow']
            # Update traces and draw each bot
            for b, pos in enumerate(positions):
                if pos is None:
                    continue
                xdraw, ydraw = pos
                # Extend trace history for this bot
                while len(st.session_state.traces) <= b:
                    st.session_state.traces.append([])
                st.session_state.traces[b].append((xdraw, ydraw))
                # Plot trace
                xs = [p[0] for p in st.session_state.traces[b]]
                ys = [p[1] for p in st.session_state.traces[b]]
                ax.plot(xs, ys, color=colors[b], linewidth=2, alpha=0.6)
                # Plot current position
                ax.scatter(xdraw, ydraw, s=300, c=colors[b], marker='o')
                ax.text(xdraw, ydraw, str(b + 1), color='white',
                        ha='center', va='center', fontsize=12)
            # Configure axes: invert x to match controller coordinate orientation,
            # keep y as-is so row 0 is at the bottom
            ax.set_xticks(range(w))
            ax.set_yticks(range(h))
            ax.set_xlim(-0.5, w - 0.5)
            ax.set_ylim(-0.5, h - 0.5)
            # Do not invert axes: row 0 appears at the bottom and column 0 at the left
            ax.set_aspect('equal')
            placeholder.pyplot(fig)

        # Add controls for automatic and manual stepping
        if st.button('Play Animation'):
            # Reset trace history and start from current step
            st.session_state.traces = [[] for _ in range(4)]
            # Play remaining frames
            for i in range(st.session_state.sim_step, len(st.session_state.frames)):
                draw_frame(i)
                time.sleep(0.5)
                st.session_state.sim_step = i + 1
        if st.button('Next Frame'):
            if st.session_state.sim_step < len(st.session_state.frames):
                draw_frame(st.session_state.sim_step)
                st.session_state.sim_step += 1
            else:
                st.info('Simulation finished')
        if st.button('Reset Simulation'):
            st.session_state.traces = [[] for _ in range(4)]
            st.session_state.sim_step = 0
            # Draw first frame if available
            if st.session_state.frames:
                draw_frame(0)

else:
    if mode == 'Simulate Steps':
        st.info("No steps available. Use 'Place Bots' or 'Import Steps'.")
