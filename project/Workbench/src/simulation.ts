const RAD_TO_DEG = 180 / Math.PI;
const DEG_TO_RAD = Math.PI / 180;

export type SimulationConfig = {
  target: number;
  kp: number;
  ki: number;
  kd: number;
  carAcceleration: number;
  feedforwardEnabled: boolean;
  damping: number;
  gravity: number;
  inertiaRatio: number;
  tiltLimitDeg: number;
  motorAngleKp: number;
  motorAngleKd: number;
  motorMaxVelocityDegS: number;
  motorMaxAccelerationDegS2: number;
};

export type SimulationState = {
  position: number;
  velocity: number;
  acceleration: number;
  tiltDeg: number;
  tiltCommandDeg: number;
  feedbackDeg: number;
  feedforwardDeg: number;
  tiltVelocityDegS: number;
};

/**
 * Rolling-ball model in the accelerating vehicle frame.
 *
 * Positive x points toward the front/right of the vehicle. A positive rail
 * angle lowers the +x end. For a solid sphere I/(mR^2) = 2/5, therefore:
 *
 *   x_ddot = [g sin(theta) - a_car cos(theta)] / (1 + 2/5) - c x_dot
 *   theta_ff = atan(a_car / g)
 *
 * Position is stored in cm for the UI; velocity and acceleration are cm/s and
 * cm/s^2. Acceleration inputs and the force equation use SI units internally.
 */
export class BallSimulation {
  state: SimulationState = {
    position: 0,
    velocity: 0,
    acceleration: 0,
    tiltDeg: 0,
    tiltCommandDeg: 0,
    feedbackDeg: 0,
    feedforwardDeg: 0,
    tiltVelocityDegS: 0,
  };

  config: SimulationConfig = {
    target: 0,
    kp: 0.28,
    ki: 0,
    kd: 0.22,
    carAcceleration: 1,
    feedforwardEnabled: true,
    damping: 0.55,
    gravity: 9.80665,
    inertiaRatio: 2 / 5,
    tiltLimitDeg: 12,
    motorAngleKp: 260,
    motorAngleKd: 30,
    motorMaxVelocityDegS: 180,
    motorMaxAccelerationDegS2: 1000,
  };

  running = false;
  private integralError = 0;

  reset(position = 0) {
    this.integralError = 0;
    this.state = {
      position,
      velocity: 0,
      acceleration: 0,
      tiltDeg: 0,
      tiltCommandDeg: 0,
      feedbackDeg: 0,
      feedforwardDeg: this.feedforwardAngleDeg(),
      tiltVelocityDegS: 0,
    };
    this.refreshDiagnostics();
  }

  disturb(impulseCmS = 24) {
    this.state.velocity += impulseCmS;
  }

  refreshDiagnostics() {
    const error = this.config.target - this.state.position;
    const feedback =
      this.config.kp * error +
      this.config.ki * this.integralError -
      this.config.kd * this.state.velocity;
    const feedforward = this.config.feedforwardEnabled ? this.feedforwardAngleDeg() : 0;

    this.state.feedbackDeg = feedback;
    this.state.feedforwardDeg = feedforward;
    this.state.tiltCommandDeg = this.clampTilt(feedback + feedforward);
    this.state.acceleration = this.ballAccelerationCmS2(this.state.tiltDeg);
    return this.state;
  }

  update(dt: number) {
    if (!this.running || dt <= 0) return this.refreshDiagnostics();

    const error = this.config.target - this.state.position;
    this.integralError = Math.max(-40, Math.min(40, this.integralError + error * dt));
    this.refreshDiagnostics();

    const angleError = this.state.tiltCommandDeg - this.state.tiltDeg;
    const angularAcceleration = Math.max(
      -this.config.motorMaxAccelerationDegS2,
      Math.min(
        this.config.motorMaxAccelerationDegS2,
        this.config.motorAngleKp * angleError - this.config.motorAngleKd * this.state.tiltVelocityDegS,
      ),
    );
    this.state.tiltVelocityDegS = Math.max(
      -this.config.motorMaxVelocityDegS,
      Math.min(
        this.config.motorMaxVelocityDegS,
        this.state.tiltVelocityDegS + angularAcceleration * dt,
      ),
    );
    this.state.tiltDeg += this.state.tiltVelocityDegS * dt;
    this.state.acceleration = this.ballAccelerationCmS2(this.state.tiltDeg);
    this.state.velocity += this.state.acceleration * dt;
    this.state.position += this.state.velocity * dt;

    if (this.state.position > 12) {
      this.state.position = 12;
      this.state.velocity *= -0.18;
      this.integralError *= 0.5;
    } else if (this.state.position < -12) {
      this.state.position = -12;
      this.state.velocity *= -0.18;
      this.integralError *= 0.5;
    }

    return this.state;
  }

  private feedforwardAngleDeg() {
    return Math.atan2(this.config.carAcceleration, this.config.gravity) * RAD_TO_DEG;
  }

  private ballAccelerationCmS2(tiltDeg: number) {
    const theta = tiltDeg * DEG_TO_RAD;
    const rollingAcceleration =
      (this.config.gravity * Math.sin(theta) - this.config.carAcceleration * Math.cos(theta)) /
      (1 + this.config.inertiaRatio);
    const velocityMps = this.state.velocity / 100;
    return (rollingAcceleration - this.config.damping * velocityMps) * 100;
  }

  private clampTilt(value: number) {
    return Math.max(-this.config.tiltLimitDeg, Math.min(this.config.tiltLimitDeg, value));
  }
}
