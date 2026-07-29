export type SimulationConfig = {
  target: number;
  kp: number;
  kd: number;
  damping: number;
};

export type SimulationState = {
  position: number;
  velocity: number;
  tiltDeg: number;
};

export class BallSimulation {
  state: SimulationState = { position: 0, velocity: 0, tiltDeg: 0 };
  config: SimulationConfig = { target: 0, kp: 1.25, kd: 0.78, damping: 0.42 };
  running = false;

  reset(position = 0) {
    this.state = { position, velocity: 0, tiltDeg: 0 };
  }

  disturb(impulse = 3.2) {
    this.state.velocity += impulse;
  }

  update(dt: number) {
    if (!this.running) return this.state;
    const error = this.config.target - this.state.position;
    const command = this.config.kp * error - this.config.kd * this.state.velocity;
    const tiltDeg = Math.max(-12, Math.min(12, command));
    const acceleration = 9.81 * Math.sin((tiltDeg * Math.PI) / 180) - this.config.damping * this.state.velocity;
    this.state.velocity += acceleration * dt;
    this.state.position += this.state.velocity * dt;

    if (this.state.position > 12) {
      this.state.position = 12;
      this.state.velocity *= -0.25;
    } else if (this.state.position < -12) {
      this.state.position = -12;
      this.state.velocity *= -0.25;
    }
    this.state.tiltDeg = tiltDeg;
    return this.state;
  }
}

