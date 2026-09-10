function P50B_PlotBusbars(G,Layout,Bus)
%% ============================================================
% 3-D busbar visualization
%% ============================================================

    figure( ...
        "Name","P50B Busbar Network", ...
        "Color","white");

    hold on;
    axis equal;
    grid on;

    xlabel("X [m]");
    ylabel("Y [m]");
    zlabel("Z [m]");

    title("P50B 26S21P — Electrical Interconnect Layout");

    %% ---------------------------------------------------------
    % Draw group collector locations
    %% ---------------------------------------------------------

    for g = 1:G.Pack.SeriesGroups

        gx = Layout.Groups.X(g);
        gy = Layout.Groups.Y(g);
        gz = Layout.Groups.Z(g);

        zTop = ...
            gz + G.Cell.Height + 1e-3;

        zBottom = ...
            gz - 1e-3;

        collectorWidth = ...
            G.Group.Width - ...
            2*G.Busbar.EdgeClearance;

        collectorDepth = ...
            G.Group.Depth - ...
            2*G.Busbar.EdgeClearance;

        %% Draw top collector

        drawBox( ...
            gx - collectorWidth/2, ...
            gy - collectorDepth/2, ...
            zTop, ...
            collectorWidth, ...
            collectorDepth, ...
            G.Busbar.Thickness);

        %% Draw bottom collector

        drawBox( ...
            gx - collectorWidth/2, ...
            gy - collectorDepth/2, ...
            zBottom, ...
            collectorWidth, ...
            collectorDepth, ...
            G.Busbar.Thickness);

        %% Group number

        text( ...
            gx, ...
            gy, ...
            zTop + 0.005, ...
            sprintf("G%02d",g), ...
            "HorizontalAlignment","center", ...
            "FontWeight","bold");

    end

    %% ---------------------------------------------------------
    % Draw series links
    %% ---------------------------------------------------------

    for k = 1:height(Bus.SeriesLinks)

        g1 = Bus.SeriesLinks.FromGroup(k);
        g2 = Bus.SeriesLinks.ToGroup(k);

        x1 = Layout.Groups.X(g1);
        y1 = Layout.Groups.Y(g1);

        x2 = Layout.Groups.X(g2);
        y2 = Layout.Groups.Y(g2);

        %% Surface

        if Bus.SeriesLinks.LinkSurface(k) == "TOP"

            z1 = Layout.Groups.Z(g1) + G.Cell.Height;

            z2 = Layout.Groups.Z(g2) + G.Cell.Height;

        else

            z1 = Layout.Groups.Z(g1);

            z2 = Layout.Groups.Z(g2);

        end

        %% Draw link

        drawBusbar( ...
            [x1 y1 z1], ...
            [x2 y2 z2], ...
            G.Busbar.Thickness, ...
            Bus.SeriesWidth);

    end

    %% ---------------------------------------------------------
    % Pack terminals
    %% ---------------------------------------------------------

    %% Negative = top of G1

    g = 1;

    x = Layout.Groups.X(g);
    y = Layout.Groups.Y(g);
    z = Layout.Groups.Z(g)+G.Cell.Height;

    drawBusbar( ...
        [x y z], ...
        [x-0.08 y z], ...
        G.Busbar.Thickness, ...
        25e-3);

    text( ...
        x-0.08, ...
        y, ...
        z+0.01, ...
        "PACK -", ...
        "FontWeight","bold");

    %% Positive = top of G26

    g = 26;

    x = Layout.Groups.X(g);
    y = Layout.Groups.Y(g);
    z = Layout.Groups.Z(g)+G.Cell.Height;

    drawBusbar( ...
        [x y z], ...
        [x+0.08 y z], ...
        G.Busbar.Thickness, ...
        25e-3);

    text( ...
        x+0.08, ...
        y, ...
        z+0.01, ...
        "PACK +", ...
        "FontWeight","bold");

    %% ---------------------------------------------------------
    % View
    %% ---------------------------------------------------------

    view(35,25);

    camlight;
    lighting gouraud;

end


%% =============================================================
% Rectangular box
%% =============================================================

function drawBox(x,y,z,L,W,H)

    V = [ ...
        x   y   z;
        x+L y   z;
        x+L y+W z;
        x   y+W z;
        x   y   z+H;
        x+L y   z+H;
        x+L y+W z+H;
        x   y+W z+H];

    F = [ ...
        1 2 3 4;
        5 6 7 8;
        1 2 6 5;
        2 3 7 6;
        3 4 8 7;
        4 1 5 8];

    patch( ...
        "Vertices",V, ...
        "Faces",F, ...
        "FaceAlpha",0.55, ...
        "EdgeColor","k");

end


%% =============================================================
% Busbar between two points
%% =============================================================

function drawBusbar(p1,p2,thickness,width)

    d = p2-p1;

    L = norm(d);

    if L < eps
        return;
    end

    n = d/L;

    %% Pick reference vector

    ref = [0 0 1];

    if abs(dot(n,ref)) > 0.9
        ref = [0 1 0];
    end

    u = cross(n,ref);
    u = u/norm(u);

    v = cross(n,u);
    v = v/norm(v);

    %% Half dimensions

    hw = width/2;
    ht = thickness/2;

    %% Vertices

    V = [ ...
        p1 + hw*u + ht*v;
        p1 - hw*u + ht*v;
        p1 - hw*u - ht*v;
        p1 + hw*u - ht*v;
        p2 + hw*u + ht*v;
        p2 - hw*u + ht*v;
        p2 - hw*u - ht*v;
        p2 + hw*u - ht*v];

    %% Faces

    F = [ ...
        1 2 3 4;
        5 6 7 8;
        1 2 6 5;
        2 3 7 6;
        3 4 8 7;
        4 1 5 8];

    patch( ...
        "Vertices",V, ...
        "Faces",F, ...
        "FaceAlpha",0.9, ...
        "EdgeColor","k");

end

