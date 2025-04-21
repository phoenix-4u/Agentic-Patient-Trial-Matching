import React from 'react';
import './App.css';
import ClinicalTrialMatcher from './ClinicalTrialMatcher.jsx';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Box from '@mui/material/Box'; // Import Box

function App() {
  return (
    <Box sx={{ flexGrow: 1 }}> {/* Use Box for flexGrow */}
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            AI Clinical Trial Matching Demo
          </Typography>
        </Toolbar>
      </AppBar>
      <Container component="main" sx={{ mt: 4, mb: 4 }}> {/* Add top/bottom margin */}
        <ClinicalTrialMatcher />
      </Container>
    </Box>
  );
}

export default App;