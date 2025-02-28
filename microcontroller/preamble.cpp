#include <Arduino.h>
#include <math.h>


class PumpConnection{
  private:
    unsigned int _identifier;
    unsigned int _pwm;
    unsigned int _tacho;
    static unsigned int _numInstances;
  public:
    PumpConnection(unsigned int pwm, unsigned int tacho){
      _pwm = pwm;
      _tacho = tacho;
      _identifier = _numInstances;
      _numInstances++;
      pinMode(pwm,OUTPUT);
      pinMode(tacho,INPUT);
    }
    unsigned int pwm_pin() const {
      return _pwm;
    }
    unsigned int tacho_pin() const {
      return _tacho;
    }
    unsigned int identifier() const {
      return _identifier;
    }
}