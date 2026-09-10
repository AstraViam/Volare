function P50B_PlotCells(G,Cells)
%% ============================================================
% P50B_PlotCells
%
% 3D visualization of all 546 cylindrical cells.
%% ============================================================

figure( ...
    "Name","P50B 546 Cell Mechanical Layout", ...
    "Color","white");

hold on;
axis equal;
grid on;

xlabel("X [m]");
ylabel("Y [m]");
zlabel("Z [m]");

title("Molicel P50B 26S21P — 546 Cell Layout");

%% Cylinder geometry

n = 16;

[cx,cy,cz] = cylinder( ...
    G.Cell.Radius,n);

cz = cz * G.Cell.Height;

%% Draw cells

for i = 1:height(Cells)

    X = cx + Cells.X(i);

    Y = cy + Cells.Y(i);

    Z = cz + Cells.Z(i);

    surf( ...
        X,Y,Z, ...
        "EdgeColor","none", ...
        "FaceAlpha",0.75);

end

%% Plot group centres

for g = 1:G.Pack.SeriesGroups

    idx = Cells.SeriesGroup == g;

    gx = mean(Cells.X(idx));

    gy = mean(Cells.Y(idx));

    gz = mean(Cells.Z(idx));

    text( ...
        gx, ...
        gy, ...
        gz + G.Cell.Height, ...
        sprintf("G%02d",g), ...
        "HorizontalAlignment","center", ...
        "FontWeight","bold");

end

%% Improve view

view(35,25);

camlight;
lighting gouraud;

end
