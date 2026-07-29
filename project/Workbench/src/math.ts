export type CalibrationSample = {
  id: number;
  trueX: number;
  u: number;
  v: number;
};

export type MappingModel = {
  name: string;
  estimate: (u: number, v: number) => number;
  formula: string;
};

function solveLinearSystem(matrix: number[][], vector: number[]): number[] {
  const n = vector.length;
  const augmented = matrix.map((row, index) => [...row, vector[index]]);

  for (let column = 0; column < n; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < n; row += 1) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) {
        pivot = row;
      }
    }
    if (Math.abs(augmented[pivot][column]) < 1e-10) {
      throw new Error("标定点不足或几何关系退化");
    }
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];

    const divisor = augmented[column][column];
    for (let index = column; index <= n; index += 1) {
      augmented[column][index] /= divisor;
    }
    for (let row = 0; row < n; row += 1) {
      if (row === column) continue;
      const factor = augmented[row][column];
      for (let index = column; index <= n; index += 1) {
        augmented[row][index] -= factor * augmented[column][index];
      }
    }
  }
  return augmented.map((row) => row[n]);
}

function leastSquares(rows: number[][], values: number[]): number[] {
  const columns = rows[0].length;
  const ata = Array.from({ length: columns }, () => Array(columns).fill(0));
  const atb = Array(columns).fill(0);
  for (let row = 0; row < rows.length; row += 1) {
    for (let i = 0; i < columns; i += 1) {
      atb[i] += rows[row][i] * values[row];
      for (let j = 0; j < columns; j += 1) {
        ata[i][j] += rows[row][i] * rows[row][j];
      }
    }
  }
  return solveLinearSystem(ata, atb);
}

export function fitLinear(samples: CalibrationSample[]): MappingModel {
  if (samples.length < 2) throw new Error("线性映射至少需要 2 个标定点");
  const [a, b] = leastSquares(
    samples.map((sample) => [sample.u, 1]),
    samples.map((sample) => sample.trueX),
  );
  return {
    name: "一维线性",
    estimate: (u) => a * u + b,
    formula: `x = ${a.toFixed(5)}u ${b >= 0 ? "+" : "-"} ${Math.abs(b).toFixed(3)}`,
  };
}

export function fitProjective(samples: CalibrationSample[]): MappingModel {
  if (samples.length < 3) throw new Error("射影映射至少需要 3 个标定点");
  const [a, b, c] = leastSquares(
    samples.map((sample) => [sample.u, 1, -sample.trueX * sample.u]),
    samples.map((sample) => sample.trueX),
  );
  return {
    name: "一维射影",
    estimate: (u) => (a * u + b) / (c * u + 1),
    formula: `x = (${a.toFixed(4)}u ${b >= 0 ? "+" : "-"} ${Math.abs(b).toFixed(2)}) / (${c.toFixed(6)}u + 1)`,
  };
}

export function fitHomography(
  imagePoints: Array<[number, number]>,
  physicalPoints: Array<[number, number]>,
): MappingModel {
  if (imagePoints.length !== 4 || physicalPoints.length !== 4) {
    throw new Error("单应性需要 4 对不共线点");
  }
  const rows: number[][] = [];
  const values: number[] = [];
  for (let index = 0; index < 4; index += 1) {
    const [u, v] = imagePoints[index];
    const [x, y] = physicalPoints[index];
    rows.push([u, v, 1, 0, 0, 0, -x * u, -x * v]);
    values.push(x);
    rows.push([0, 0, 0, u, v, 1, -y * u, -y * v]);
    values.push(y);
  }
  const h = solveLinearSystem(rows, values);
  return {
    name: "二维单应性",
    estimate: (u, v) => {
      const scale = h[6] * u + h[7] * v + 1;
      return (h[0] * u + h[1] * v + h[2]) / scale;
    },
    formula: "s[X,Y,1]ᵀ = H[u,v,1]ᵀ",
  };
}

export function mappingStats(model: MappingModel, samples: CalibrationSample[]) {
  const errors = samples.map((sample) => model.estimate(sample.u, sample.v) - sample.trueX);
  const rmse = Math.sqrt(errors.reduce((sum, value) => sum + value * value, 0) / Math.max(1, errors.length));
  const maxError = errors.reduce((maximum, value) => Math.max(maximum, Math.abs(value)), 0);
  return { errors, rmse, maxError };
}

