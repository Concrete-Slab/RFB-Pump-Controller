void sendSpeed(int i, long rpm){
    // this is the name,value method!
    Serial.print(startChar);
    Serial.print(pumps[i].name);
    Serial.print(',');
    Serial.print(rpm);
    Serial.print(endChar);
  }