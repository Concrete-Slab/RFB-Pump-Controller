void sendSpeed(int i, long rpm){
  //This is the comma separated values method!
  Serial.print(rpm);
  // if last pump, don't include comma!
  if (i<numPumps-1){
    Serial.print(',');
  }
}